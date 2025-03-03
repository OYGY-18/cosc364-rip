from config import Config
from rip import RIP
import sys

def main():
    """Main entry point for the RIP routing daemon.
    Parses the given configuration file, initializes the router, and starts the RIP routing process.
    """
    # Expect exactly one command-line argument: the config file path
    if len(sys.argv) != 2:
        print("Usage: python3 main.py <config_file>")
        sys.exit(1)
    config_file = sys.argv[1]

    # Initialize and parse router configuration
    config = Config(config_file)
    config.parse_config()   # Validate router_id, input_ports, outputs as per spec

    # (Socket binding is handled in RIP initialization to avoid double-binding)
    print(f"Router {config.router_id}: Configuration loaded successfully.")

    # Initialize the RIP routing engine with parsed configuration
    rip = RIP(config.router_id, config.input_ports, config.neighbors)
    print(f"Router {config.router_id}: RIP routing engine started. Listening for messages...")

    # Enter the main loop to receive and process RIP messages (runs until termination)
    rip.receive_rip_messages()

if __name__ == '__main__':
    main()
