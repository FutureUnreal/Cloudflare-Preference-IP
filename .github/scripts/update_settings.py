import json
import os
from pathlib import Path

def update_settings():
    # 读取配置文件
    config_path = Path('config/settings.json')
    with open(config_path) as f:
        settings = json.load(f)
    
    # 阿里云配置
    settings['dns']['providers']['aliyun']['access_key_id'] = os.environ.get('ALIYUN_KEY', '')
    settings['dns']['providers']['aliyun']['access_key_secret'] = os.environ.get('ALIYUN_SECRET', '')
    
    # 添加 DNSPod 配置
    settings['dns']['providers']['dnspod']['secret_id'] = os.environ.get('DNSPOD_ID', '')
    settings['dns']['providers']['dnspod']['secret_key'] = os.environ.get('DNSPOD_KEY', '')
    
    # 添加华为云配置
    settings['dns']['providers']['huawei']['ak'] = os.environ.get('HUAWEI_AK', '')
    settings['dns']['providers']['huawei']['sk'] = os.environ.get('HUAWEI_SK', '')

    # 更新域名配置
    domain = os.environ.get('DOMAIN', '')
    subdomain = os.environ.get('SUBDOMAIN', '')
    if domain:
        settings['domains'] = {domain: {"@": settings['domains']['$DOMAIN']['$SUBDOMAIN']}}
        if subdomain:
            settings['domains'][domain][subdomain] = settings['domains']['$DOMAIN']['$SUBDOMAIN']
    
    # 保存更新后的配置
    with open(config_path, 'w') as f:
        json.dump(settings, f, indent=2)

if __name__ == '__main__':
    update_settings()