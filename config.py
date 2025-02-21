import configparser
import socket
import sys
from port_validator import PortValidator

class Config:
    def __init__(self, config_file):
        self.config_file = config_file
        self.router_id = None
        self.input_ports = []
        self.outputs = []
        self.neighbors = {}

    def validate_router_id(self, router_id):
        router_id = int(router_id)
        if 1 <= router_id <= 64000:
            return router_id
        raise ValueError("Router ID must be between 1 and 64000")

    def validate_cost(self, cost):
        cost = int(cost)
        if 1 <= cost <= 15:
            return cost
        raise ValueError("Cost must be between 1 and 15")

    def parse_config(self):
        config = configparser.ConfigParser()
        try:
            config.read(self.config_file)
            self.router_id = self.validate_router_id(config['Router_Info']['router_id'])

            input_ports_str = config['Router_Info']['input_ports']
            for port_str in input_ports_str.split(', '):
                self.input_ports.append(PortValidator.validate_port(port_str))

            output_strs = config['Router_Info']['outputs'].split(', ')
            for output_str in output_strs:
                port, cost, router_id = output_str.split('-')
                port = PortValidator.validate_port(port)
                cost = self.validate_cost(cost)
                router_id = self.validate_router_id(router_id)
                self.outputs.append((port, cost, router_id))
                self.neighbors[router_id] = port

            PortValidator.check_duplicate_ports(self.input_ports + [o[0] for o in self.outputs])
            PortValidator.check_input_output_conflict(self.input_ports, [o[0] for o in self.outputs])

        except KeyError as e:
            print(f"Missing key in config file: {e}")
            sys.exit(1)
        except ValueError as e:
            print(f"Invalid value in config file: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"Error parsing config file: {e}")
            sys.exit(1)

    def create_sockets(self):
        self.sockets = []
        for port in self.input_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.bind(("localhost", port))
                self.sockets.append(sock)
            except Exception as e:
                print(f"Failed to bind socket on port {port}: {e}")
                sys.exit(1)
