import json
import logging
from aliyunsdkcore import client
from aliyunsdkalidns.request.v20150109 import (
    DescribeDomainRecordsRequest,
    DeleteDomainRecordRequest,
    UpdateDomainRecordRequest,
    AddDomainRecordRequest
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('AliDNS')

class AliDNS:
    def __init__(self, access_key_id: str, access_key_secret: str, region: str = 'cn-hangzhou'):
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        self.region = region
        self.client = client.AcsClient(access_key_id, access_key_secret, region)
        self._format = 'json'

    def get_record(self, domain: str, length: int, sub_domain: str, record_type: str) -> dict:
        request = DescribeDomainRecordsRequest.DescribeDomainRecordsRequest()
        logger.info(f"查询记录参数: domain={domain}, length={length}, sub_domain={sub_domain}, record_type={record_type}")
        request.set_DomainName(domain)
        request.set_PageSize(length)
        request.set_RRKeyWord(sub_domain)
        request.set_Type(record_type)
        request.set_accept_format(self._format)
        
        result = self.client.do_action(request).decode('utf-8')
        result = result.replace('DomainRecords', 'data', 1)\
                      .replace('Record', 'records', 1)\
                      .replace('RecordId', 'id')\
                      .replace('Value', 'value')\
                      .replace('Line', 'line')\
                      .replace('telecom', '电信')\
                      .replace('unicom', '联通')\
                      .replace('mobile', '移动')\
                      .replace('oversea', '境外')\
                      .replace('default', '默认')
        
        return json.loads(result)

    def create_record(self, domain: str, sub_domain: str, value: str, 
                     record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        logger.info(f"创建记录参数: domain={domain}, sub_domain={sub_domain}, value={value}, type={record_type}, line={line}, ttl={ttl}")
        
        request = AddDomainRecordRequest.AddDomainRecordRequest()
        request.set_DomainName(domain)
        request.set_RR(sub_domain)
        request.set_Type(record_type)
        request.set_Value(value)
        request.set_TTL(ttl)
        
        # 线路转换
        line_map = {
            "电信": "telecom",
            "联通": "unicom",
            "移动": "mobile",
            "境外": "oversea",
            "默认": "default"
        }
        mapped_line = line_map.get(line, line)
        request.set_Line(mapped_line)
        request.set_accept_format(self._format)
        
        # 打印完整请求参数
        request_params = {
            'DomainName': domain,
            'RR': sub_domain,
            'Type': record_type,
            'Value': value,
            'Line': mapped_line,
            'TTL': ttl
        }
        logger.info(f"完整请求参数: {json.dumps(request_params, ensure_ascii=False)}")
        
        result = self.client.do_action(request).decode('utf-8')
        return json.loads(result)

    def update_record(self, domain: str, record_id: str, sub_domain: str,
                     value: str, record_type: str = "A", line: str = "默认", ttl: int = 600) -> dict:
        request = UpdateDomainRecordRequest.UpdateDomainRecordRequest()
        request.set_RecordId(record_id)
        request.set_RR(sub_domain)
        request.set_Type(record_type)
        request.set_Value(value)
        request.set_TTL(ttl)
        
        # 线路转换
        line_map = {
            "电信": "telecom",
            "联通": "unicom",
            "移动": "mobile",
            "境外": "oversea",
            "默认": "default"
        }
        request.set_Line(line_map.get(line, line))
        request.set_accept_format(self._format)
        
        result = self.client.do_action(request).decode('utf-8')
        return json.loads(result)

    def delete_record(self, domain: str, record_id: str) -> dict:
        request = DeleteDomainRecordRequest.DeleteDomainRecordRequest()
        request.set_RecordId(record_id)
        request.set_accept_format(self._format)
        
        result = self.client.do_action(request).decode('utf-8')
        return json.loads(result)