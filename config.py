import configparser
import socket
import sys
from port_validator import PortValidator

class Config:
    """Parses and validates the router configuration file for the RIP routing daemon.

    This class reads an ASCII configuration file (expected INI format with a [Router_Info] section) 
    that contains router settings, validates all parameters, and provides attributes for router ID, 
    input ports, and outputs (neighbors). It also provides a method to create UDP sockets for the input ports.

    The configuration file must define the following parameters (one per line, within the [Router_Info] section):
    - router_id: Unique identifier for this router (integer 1 to 64000 inclusive)&#8203;:contentReference[oaicite:16]{index=16}.
    - input_ports: Comma-separated list of local UDP port numbers on which this router listens (each 1024-64000)&#8203;:contentReference[oaicite:17]{index=17}.
    - outputs: Comma-separated list of neighbor specifications in the format "<port>-<cost>-<router_id>"&#8203;:contentReference[oaicite:18]{index=18}.
      Each neighbor entry defines a link to another router, where:
        * <port> is the UDP port on the neighbor router to send packets to (must satisfy same range as input_ports&#8203;:contentReference[oaicite:19]{index=19}),
        * <cost> is the RIP metric (1-15) for the link&#8203;:contentReference[oaicite:20]{index=20}&#8203;:contentReference[oaicite:21]{index=21},
        * <router_id> is the unique ID of the neighbor router (1-64000).
    
    The configuration parser will ensure:
    - All required parameters are present; otherwise, the program exits with an error.
    - Router ID is within the valid range&#8203;:contentReference[oaicite:22]{index=22}.
    - Port numbers are integers in the valid range (1024-64000)&#8203;:contentReference[oaicite:23]{index=23}.
    - No port number is listed more than once across input_ports and outputs&#8203;:contentReference[oaicite:24]{index=24}.
    - No port number appears in both input_ports and outputs (avoids port conflicts)&#8203;:contentReference[oaicite:25]{index=25}.
    - No output entry has this router's own ID as the neighbor (a router cannot list itself as a neighbor).
    - Each output entry is correctly formatted and has valid values.
    
    If any check fails, a descriptive error is printed and the program will exit.
    """
    def __init__(self, config_file):
        """Initialize the Config parser with the given configuration file path."""
        self.config_file = config_file
        self.router_id = None
        self.input_ports = []
        self.outputs = []
        # neighbors maps neighbor router IDs to their corresponding UDP port (for sending packets)
        self.neighbors = {}

    def validate_router_id(self, router_id):
        """Validate and return router_id as an integer within [1, 64000]."""
        try:
            router_id = int(router_id)
        except ValueError:
            raise ValueError("Router ID must be an integer")
        if 1 <= router_id <= 64000:
            return router_id
        # Outside allowed range
        raise ValueError("Router ID must be between 1 and 64000 (inclusive)")

    def validate_cost(self, cost):
        """Validate and return cost (metric) as an integer within [1, 15]."""
        try:
            cost = int(cost)
        except ValueError:
            raise ValueError("Cost (metric) must be an integer")
        if 1 <= cost <= 15:
            return cost
        # RIP metric 16 is considered infinity (unreachable)&#8203;:contentReference[oaicite:26]{index=26}, so disallow setting cost=16 in config.
        raise ValueError("Cost must be between 1 and 15 (inclusive)")

    def parse_config(self):
        """Parse the configuration file and populate router_id, input_ports, outputs, and neighbors.

        This method reads the configuration file, extracts required parameters, and validates each.
        On success, the Config object will have:
         - router_id: int
         - input_ports: list of int (the ports this router listens on)
         - outputs: list of tuples (neighbor_port, cost, neighbor_id) for each neighbor
         - neighbors: dict mapping neighbor_id -> neighbor_port for quick access when sending packets.

        It performs necessary validation checks on the values as per the assignment specification&#8203;:contentReference[oaicite:27]{index=27}&#8203;:contentReference[oaicite:28]{index=28}.
        If the config file is missing required fields or contains invalid values, the program will print an error and exit.
        """
        config = configparser.ConfigParser()
        # ConfigParser will treat lines starting with '#' or ';' as comments by default.
        try:
            # Read the file; configparser ignores blank lines and full-line comments.
            config.read(self.config_file)
            # Ensure the expected section and keys exist
            if 'Router_Info' not in config:
                raise KeyError("Router_Info section missing")
            router_info = config['Router_Info']

            # Router ID (required)
            if 'router_id' not in router_info:
                raise KeyError("router_id")
            raw_router_id = router_info['router_id']
            router_id_val = raw_router_id.split('#')[0].split(';')[0].strip()
            self.router_id = self.validate_router_id(router_id_val)

            # Input ports (required)
            if 'input_ports' not in router_info:
                raise KeyError("input_ports")
            input_ports_str = router_info['input_ports'].split('#')[0].split(';')[0].strip()
            # Split by comma and strip whitespace, allowing formats like "port1, port2" or "port1,port2"
            input_port_list = [p.strip() for p in input_ports_str.split(',') if p.strip() != '']
            if not input_port_list:
                raise ValueError("Input ports list is empty or incorrectly formatted")
            for port_str in input_port_list:
                # Validate each port and add to list
                self.input_ports.append(PortValidator.validate_port(port_str))

            # Outputs (required)
            if 'outputs' not in router_info:
                raise KeyError("outputs")
            outputs_str = router_info['outputs'].split('#')[0].split(';')[0].strip()
            output_entries = [entry.strip() for entry in outputs_str.split(',') if entry.strip() != '']
            if not output_entries:
                raise ValueError("Outputs list is empty or incorrectly formatted")
            for entry in output_entries:
                # Each entry should be in the form "port-cost-routerID"
                parts = entry.split('-')
                if len(parts) != 3:
                    raise ValueError(f"Invalid output entry format: '{entry}'. Expected format: port-cost-router_id")
                port_str, cost_str, rid_str = parts
                # Validate each component
                port = PortValidator.validate_port(port_str)
                cost = self.validate_cost(cost_str)
                neighbor_id = self.validate_router_id(rid_str)
                if neighbor_id == self.router_id:
                    raise ValueError(f"Output entry {entry}: Router cannot list itself as a neighbor")
                if neighbor_id in self.neighbors:
                    # Each neighbor router_id should be listed only once
                    raise ValueError(f"Duplicate neighbor router ID {neighbor_id} in outputs")
                # All validations passed for this neighbor entry
                self.outputs.append((port, cost, neighbor_id))
                self.neighbors[neighbor_id] = port

            # Check for duplicate port numbers in input_ports and output ports
            PortValidator.check_duplicate_ports(self.input_ports)
            PortValidator.check_duplicate_ports([o[0] for o in self.outputs])
            # Ensure no input port is also used as an output port (port conflict)
            PortValidator.check_input_output_conflict(self.input_ports, [o[0] for o in self.outputs])
        except KeyError as e:
            # Missing mandatory configuration key
            print(f"Missing key in config file: {e}")
            sys.exit(1)
        except ValueError as e:
            # One of the validation checks failed
            print(f"Invalid value in config file: {e}")
            sys.exit(1)
        except Exception as e:
            # Catch-all for any other parsing errors
            print(f"Error parsing config file: {e}")
            sys.exit(1)

    def create_sockets(self):
        """Create and bind UDP sockets for each input port.

        For each port in self.input_ports, this method creates a UDP socket and binds it to ('localhost', port).
        All sockets are stored in the self.sockets list.
        If any socket fails to bind (e.g., port is already in use), an error is printed and the program exits.
        """
        self.sockets = []
        for port in self.input_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                # Bind to localhost so that routers communicate on the local machine only
                sock.bind(("localhost", port))
                self.sockets.append(sock)
            except Exception as e:
                print(f"Failed to bind socket on port {port}: {e}")
                sys.exit(1)
