from src.dns.aliyun import AliDNS
import os

# 初始化 DNS 客户端
aliyun = AliDNS(
    access_key_id=os.environ.get('ALIYUN_KEY'),
    access_key_secret=os.environ.get('ALIYUN_SECRET'),
    region='cn-hangzhou'  # 明确使用杭州区域
)

# 先测试获取记录
result = aliyun.get_record(
    domain='ai-unreal.top',
    length=1,
    sub_domain='',
    record_type='A'
)
print(f"查询结果: {result}")

# 测试添加记录
try:
    create_result = aliyun.create_record(
        domain='ai-unreal.top',
        sub_domain='cdn',
        value='1.1.1.3',
        record_type='A',
        line='默认',
        ttl=600
    )
    print(f"添加记录结果: {create_result}")
except Exception as e:
    print(f"添加记录失败: {str(e)}")