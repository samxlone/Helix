from config.manager import config_manager

# Expose a simple API compatible with previous usage
config = config_manager

# Example usage: config.get('prefix') or config.as_dict()
