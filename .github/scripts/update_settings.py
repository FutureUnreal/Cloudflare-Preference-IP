import json
import os
from pathlib import Path

def update_settings():
    # 读取配置文件
    config_path = Path('config/settings.json')
    with open(config_path) as f:
        settings = json.load(f)
    
    # 更新凭证
    settings['dns']['providers']['aliyun']['access_key_id'] = os.environ.get('ALIYUN_KEY', '')
    settings['dns']['providers']['aliyun']['access_key_secret'] = os.environ.get('ALIYUN_SECRET', '')
    
    # 保存更新后的配置
    with open(config_path, 'w') as f:
        json.dump(settings, f, indent=2)

if __name__ == '__main__':
    update_settings()