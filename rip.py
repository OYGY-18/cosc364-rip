import time
import struct
import socket
import select
import sys
import signal
import threading

class RIPEntry:
    """
    Represents a routing table entry for a destination.
    """
    def __init__(self, dest_id, metric, next_hop):
        self.dest_id = dest_id  # Destination router ID
        self.metric = metric    # Distance (hop count) to destination (1-15, with 16 as infinity)
        self.next_hop = next_hop  # Next hop router ID
        self.timer = time.time()  # Last time this route was updated (for timeout tracking)

class RIPPacket:
    """
    Initialize a RIP packet with header fields.
    command: 1 for Request, 2 for Response (update)
    version: RIP version (should be 2)
    router_id: ID of the router sending the packet (carried in the RIP header unused field)
    """
    def __init__(self, command, version, router_id):
        self.command = command      # RIP command (1=Request, 2=Response)
        self.version = version      # RIP version (expect 2 for RIP v2)
        self.router_id = router_id  # Sender's router ID (using the RIP header unused field to carry this)
        self.entries = []           # List of entries (dest_id, metric, next_hop) in this packet

    def add_entry(self, dest_id, metric, next_hop):
        """
        Add a routing entry to the RIP packet.
        dest_id: destination router ID
        metric: cost to reach the destination
        next_hop: next hop router ID for this route (for informational use)
        """
        self.entries.append((dest_id, metric, next_hop))

    def pack(self):
        """
        Pack the RIPPacket into binary format for sending via UDP.
        Returns a bytes object representing the RIP packet.
        """
        # RIP header: command (1 byte), version (1 byte), unused/router_id (2 bytes)
        packet = struct.pack('>BBH', self.command, self.version, self.router_id)
        # Each entry: 20 bytes: family (2), route tag (2), IP (4), mask (4), next hop (4), metric (4)
        # Using router IDs in place of IP addresses.
        for dest_id, metric, next_hop in self.entries:
            family = 2  # Address family (IP)
            route_tag = 0
            ip_addr = dest_id
            subnet_mask = 0
            next_hop_ip = 0
            # Metric is 1-16 (16 indicates infinity/unreachable)
            packet += struct.pack('>HHIIII', family, route_tag, ip_addr, subnet_mask, next_hop_ip, metric)
        return packet

    @staticmethod
    def unpack(data):
        """
        Parse binary data into a RIPPacket object.
        Returns a RIPPacket with entries list populated, or None if invalid.
        """
        if len(data) < 4:
            return None  # Packet too short to be valid
        command, version, router_id = struct.unpack('>BBH', data[:4])
        packet = RIPPacket(command, version, router_id)
        # Validate header fields
        if version != 2 or command not in (1, 2):
            return None
        # Check that data length is 4 + 20*N
        if (len(data) - 4) % 20 != 0:
            return None
        num_entries = (len(data) - 4) // 20
        for i in range(num_entries):
            entry_data = data[4 + i*20 : 4 + (i+1)*20]
            family, route_tag, ip_addr, mask, next_hop_ip, metric = struct.unpack('>HHIIII', entry_data)
            if family not in (2, 0xFFFF) or metric < 1 or metric > 16:
                continue  # skip invalid entry
            dest_id = ip_addr
            # Use the packet's router_id as the neighbor (next hop) identifier
            packet.add_entry(dest_id, metric, router_id)
        return packet

class RIP:
    def __init__(self, router_id, input_ports, outputs):
        """
        Initialize the RIP routing process for a given router.
        router_id: this router's ID
        input_ports: list of UDP ports this router listens on for incoming RIP messages
        outputs: list of tuples (port, cost, neighbor_id) for direct neighbors
        """
        self.router_id = router_id
        self.input_ports = input_ports
        # Mapping neighbor_id to the port number for sending
        self.neighbors = {nbr_id: port for (port, cost, nbr_id) in outputs}
        # Mapping neighbor_id to the cost metric of the link
        self.link_costs = {nbr_id: cost for (port, cost, nbr_id) in outputs}
        # Initialize routing table with direct routes
        self.routing_table = {}
        # Route to self (cost 0, next hop self)
        self.routing_table[self.router_id] = RIPEntry(self.router_id, 0, self.router_id)
        # Direct neighbor routes from outputs
        for nbr_id, cost in self.link_costs.items():
            self.routing_table[nbr_id] = RIPEntry(nbr_id, cost, nbr_id)
        # Create and bind UDP sockets for input ports
        self.sockets = self.create_sockets()
        # Set up signal handler for graceful termination
        signal.signal(signal.SIGINT, self.handle_signal)
        # Lock for thread-safe operations
        self.lock = threading.Lock()
        # Start periodic updates in background
        self.start_periodic_updates()

    def create_sockets(self):
        """ 
        Create and bind UDP sockets for all input ports.
        Enables port reuse on the sockets.
        """
        sockets = []
        for port in self.input_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('localhost', port))
                sockets.append(sock)
            except OSError as e:
                print(f"Error binding to port {port}: {e}")
                sys.exit(1)
        return sockets

    def send_rip_update(self):
        """
        Send a RIP response (update) packet to all neighbors.
        Applies split horizon with poisoned reverse.
        """
        for neighbor_id, port in self.neighbors.items():
            # Create a new RIP packet for this neighbor
            packet = RIPPacket(2, 2, self.router_id)
            for dest_id, entry in self.routing_table.items():
                # If next hop is the neighbor, poison that route
                send_metric = entry.metric
                if entry.next_hop == neighbor_id:
                    send_metric = 16
                if send_metric > 16:
                    send_metric = 16
                packet.add_entry(dest_id, send_metric, entry.next_hop)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(packet.pack(), ('localhost', port))
            except Exception as e:
                print(f"Failed to send update to neighbor {neighbor_id} at port {port}: {e}")
            finally:
                sock.close()

    def receive_rip_messages(self):
        """
        Listen on input ports and process incoming RIP messages indefinitely.
        """
        while True:
            readable, _, _ = select.select(self.sockets, [], [], 1)
            for sock in readable:
                data, addr = sock.recvfrom(1024)
                # Process the message in a thread-safe manner
                with self.lock:
                    self.process_rip_message(data)

    def process_rip_message(self, data):
        """
        Parse and handle a received RIP packet.
        Updates the routing table based on the message content.
        """
        packet = RIPPacket.unpack(data)
        if packet is None:
            # Ignore invalid or non-RIP packet
            return
        if packet.command == 1:
            # RIP Request: respond with our routing table
            self.send_rip_update()
            return
        if packet.command == 2:
            # RIP Response: update routing table
            neighbor_id = packet.router_id
            if neighbor_id not in self.neighbors:
                return
            route_changed = False
            for dest_id, metric, next_hop in packet.entries:
                if dest_id == self.router_id:
                    continue
                # Calculate cost to dest via neighbor
                new_cost = self.link_costs.get(neighbor_id, float('inf')) + (metric if metric < 16 else 16)
                if new_cost > 16:
                    new_cost = 16
                if dest_id in self.routing_table:
                    entry = self.routing_table[dest_id]
                    if entry.next_hop == neighbor_id:
                        if new_cost != entry.metric:
                            entry.metric = new_cost
                            entry.timer = time.time()
                            route_changed = True
                        else:
                            entry.timer = time.time()
                    else:
                        if new_cost < entry.metric or entry.metric == 16:
                            entry.metric = new_cost
                            entry.next_hop = neighbor_id
                            entry.timer = time.time()
                            route_changed = True
                else:
                    if new_cost <= 15:
                        self.routing_table[dest_id] = RIPEntry(dest_id, new_cost, neighbor_id)
                        route_changed = True
            if route_changed:
                self.send_rip_update()
            # Print routing table after processing updates
            self.print_routing_table()

    def check_routing_table(self):
        """
        Check routing table for expired routes and handle timeouts.
        Removes or marks routes as unreachable after timeout.
        """
        current_time = time.time()
        timeout_interval = 180
        garbage_interval = 120
        for dest_id, entry in list(self.routing_table.items()):
            if dest_id == self.router_id:
                continue
            if current_time - entry.timer >= timeout_interval:
                if entry.metric != 16:
                    entry.metric = 16
                    entry.timer = current_time
                    # Trigger update to inform neighbors of unreachable route
                    self.send_rip_update()
                    print(f"Route to {dest_id} timed out. Marking as unreachable.")
                else:
                    if current_time - entry.timer >= timeout_interval + garbage_interval:
                        del self.routing_table[dest_id]
                        print(f"Removed route to {dest_id} after garbage collection.")

    def start_periodic_updates(self):
        """
        Start a background thread to send periodic RIP updates and check for timeouts.
        """
        def periodic_update():
            update_interval = 30
            while True:
                time.sleep(update_interval)
                # Perform periodic update and timeout check atomically
                with self.lock:
                    self.send_rip_update()
                    self.check_routing_table()
                    self.print_routing_table()
        threading.Thread(target=periodic_update, daemon=True).start()

    def handle_signal(self, signum, frame):
        """ Handle termination signal (e.g., Ctrl+C) to shut down the router. """
        print(f"\nRouter {self.router_id} shutting down...")
        for sock in self.sockets:
            sock.close()
        sys.exit(0)

    def print_routing_table(self):
        """
        Print the current routing table in a readable format.
        Lists all destinations with their costs, next hop, and timer.
        """
        print(f"\nRouting table of Router {self.router_id}:")
        print("Destination\tCost\tNext Hop\tTimer")
        current_time = time.time()
        for dest_id, entry in sorted(self.routing_table.items()):
            timer_val = int(current_time - entry.timer)
            nhop_display = "-" if dest_id == self.router_id else str(entry.next_hop)
            cost_display = entry.metric if entry.metric < 16 else "Inf"
            print(f"{dest_id}\t\t{cost_display}\t{nhop_display}\t\t{timer_val}s")
