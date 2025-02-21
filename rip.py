import time
import struct
import socket
import select
import sys
import signal
import threading

class RIPEntry:
    def __init__(self, dest_id, metric, next_hop):
        self.dest_id = dest_id  # 目标路由器 ID
        self.metric = metric    # 到达目标的跳数（1-15）
        self.next_hop = next_hop  # 下一跳路由器 ID
        self.timer = time.time()  # 记录更新时间

class RIPPacket:
    def __init__(self, command, version, router_id):
        self.command = command  # 1=Request, 2=Response
        self.version = version  # RIP 版本号
        self.router_id = router_id  # 发送方路由器 ID
        self.entries = []  # 存储 RIPEntry 条目

    def add_entry(self, dest_id, metric, next_hop):
        self.entries.append((dest_id, metric, next_hop))

    def pack(self):
        """ 将 RIPPacket 转换为可发送的二进制数据 """
        packet = struct.pack('>BBH', self.command, self.version, self.router_id)
        for dest_id, metric, next_hop in self.entries:
            packet += struct.pack('>HHIIII', 0, 0, 0, dest_id, 0, 0, 0, 0, metric)
        return packet

    @staticmethod
    def unpack(data):
        """ 从二进制数据解析 RIP 报文 """
        command, version, router_id = struct.unpack('>BBH', data[:4])
        packet = RIPPacket(command, version, router_id)
        num_entries = (len(data) - 4) // 20
        for i in range(num_entries):
            entry_data = data[4 + i*20 : 24 + i*20]
            _, _, _, dest_id, _, _, _, _, metric = struct.unpack('>HHIIIIIII', entry_data)
            packet.add_entry(dest_id, metric, router_id)
        return packet

class RIP:
    def __init__(self, router_id, input_ports, neighbors):
        self.router_id = router_id
        self.input_ports = input_ports
        self.neighbors = neighbors  # {neighbor_id: port}
        self.routing_table = {}  # 存储 RIPEntry
        self.sockets = self.create_sockets()
        signal.signal(signal.SIGINT, self.handle_signal)
        self.start_periodic_updates()
    
    def create_sockets(self):
        """ 创建并绑定 UDP 套接字，允许端口复用 """
        sockets = []
        for port in self.input_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 允许端口复用
                sock.bind(('localhost', port))
                sockets.append(sock)
                print(f"Router {self.router_id} bound to port {port}")
            except OSError as e:
                print(f"Error binding to port {port}: {e}")
                sys.exit(1)
        return sockets
    
    def send_rip_update(self):
        """ 发送 RIP 响应报文给邻居 """
        for neighbor_id, port in self.neighbors.items():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            packet = RIPPacket(2, 2, self.router_id)
            for dest_id, entry in self.routing_table.items():
                packet.add_entry(dest_id, entry.metric, entry.next_hop)
            sock.sendto(packet.pack(), ('localhost', port))
            sock.close()
    
    def receive_rip_messages(self):
        """ 监听端口并处理 RIP 消息 """
        while True:
            readable, _, _ = select.select(self.sockets, [], [], 1)
            for sock in readable:
                data, addr = sock.recvfrom(1024)
                self.process_rip_message(data)
    
    def process_rip_message(self, data):
        """ 解析接收到的 RIP 报文 """
        packet = RIPPacket.unpack(data)
        if packet.command == 1:  # RIP 请求，返回当前路由表
            self.send_rip_update()
        elif packet.command == 2:  # 处理 RIP 响应
            for dest_id, metric, next_hop in packet.entries:
                if dest_id == self.router_id:
                    continue
                if dest_id not in self.routing_table or metric + 1 < self.routing_table[dest_id].metric:
                    self.routing_table[dest_id] = RIPEntry(dest_id, metric + 1, next_hop)
                    self.routing_table[dest_id].timer = time.time()
    
    def check_routing_table(self):
        """ 定期检查路由表，删除超时路由 """
        current_time = time.time()
        for dest_id in list(self.routing_table.keys()):
            if current_time - self.routing_table[dest_id].timer > 180:
                del self.routing_table[dest_id]  # 超时删除
    
    def start_periodic_updates(self):
        """ 启动一个线程，每 30 秒广播 RIP 更新 """
        def periodic_update():
            while True:
                time.sleep(30)
                self.send_rip_update()
                self.check_routing_table()
                print("Periodic RIP update sent.")
        threading.Thread(target=periodic_update, daemon=True).start()
    
    def handle_signal(self, signum, frame):
        """ 处理退出信号 """
        print(f"\nRouter {self.router_id} shutting down...")
        for sock in self.sockets:
            sock.close()
        sys.exit(0)
