class PortValidator:
    """Utility class for validating port numbers and port list configurations."""
    
    @staticmethod
    def validate_port(port):
        """Validate that the given port is an integer in the range 1024–64000.
        
        Args:
            port (str or int): The port value to validate.
        Returns:
            int: The port number as an integer if valid.
        Raises:
            ValueError: If the port is not an integer or not in the valid range.
        """
        try:
            port_int = int(port)
        except ValueError:
            raise ValueError(f"Invalid port number: {port}")
        if 1024 <= port_int <= 64000:
            return port_int
        raise ValueError("Port must be between 1024 and 64000")
    
    @staticmethod
    def check_duplicate_ports(ports):
        """Check that all ports in the list are unique.
        
        Args:
            ports (list[int]): List of port numbers.
        Raises:
            ValueError: If any port number appears more than once.
        """
        if len(ports) != len(set(ports)):
            # Find duplicates for a more informative error message
            seen = set()
            duplicates = set()
            for p in ports:
                if p in seen:
                    duplicates.add(p)
                else:
                    seen.add(p)
            if duplicates:
                dup_list = ", ".join(str(d) for d in duplicates)
                raise ValueError(f"Duplicate ports detected: {dup_list}")
            else:
                raise ValueError("Duplicate ports detected")
    
    @staticmethod
    def check_input_output_conflict(input_ports, output_ports):
        """Ensure no port is listed as both an input and an output.
        
        Args:
            input_ports (list[int]): Ports designated as inputs.
            output_ports (list[int]): Ports designated as outputs.
        Raises:
            ValueError: If any port number is found in both lists.
        """
        common_ports = set(input_ports).intersection(output_ports)
        if common_ports:
            conflict_list = ", ".join(str(p) for p in common_ports)
            raise ValueError(f"Input and output ports conflict detected: {conflict_list}")
