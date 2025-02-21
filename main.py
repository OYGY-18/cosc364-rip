from config import Config
from rip import RIP
import sys

def main():
    if len(sys.argv) != 2:
        print("Usage: python main.py <config_file>")
        sys.exit(1)

    config_file = sys.argv[1]
    config = Config(config_file)
    config.parse_config()
    config.create_sockets()

    print("Configuration and socket setup completed successfully.")

    # ✅ 启动 RIP 监听
    rip = RIP(config.router_id, config.input_ports, config.neighbors)
    rip.receive_rip_messages()  # ⬅ 这行必须存在

if __name__ == '__main__':
    main()