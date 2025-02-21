class PortValidator:
    @staticmethod
    def validate_port(port):
        port = int(port)
        if 1024 <= port <= 64000:
            return port
        raise ValueError("Port must be between 1024 and 64000")

    @staticmethod
    def check_duplicate_ports(ports):
        if len(ports) != len(set(ports)):
            raise ValueError("Duplicate ports detected")

    @staticmethod
    def check_input_output_conflict(input_ports, output_ports):
        common_ports = set(input_ports).intersection(set(output_ports))
        if common_ports:
            raise ValueError(f"Input and output ports conflict detected: {common_ports}")
