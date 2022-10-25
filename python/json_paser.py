from oslo_config import cfg
import json


def init():
    register_opts(cfg.CONF)


def register_opts(conf):
    conf.register_cli_opt(
        cfg.DictOpt(
            'secret-data',
            default={}
        )
    )
    conf.register_cli_opt(
        cfg.StrOpt(
            'namespace',
            default='openstack'
        )
    )


def analyze_data(data, content):
    for k, v in data.items():
        if isinstance(v, dict):
            analyze_data(v)
        else:
            if content:
                pass


def main():
    init()
    data = json.loads('{"one" : "1", "two" : "2", "three" : "3"}')
    print(data['two'])


if __name__ == "__main__":
    main()
