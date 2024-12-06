# Cloudflare 优选 IP

[![DNS Update](https://github.com/FutureUnreal/Cloudflare-Preference-IP/actions/workflows/dns-update.yml/badge.svg)](https://github.com/FutureUnreal/Cloudflare-Preference-IP/actions/workflows/dns-update.yml)

自动测试和优化 Cloudflare IP 的工具。使用来自不同中国运营商的 ITDOG 测速节点对 Cloudflare Anycast IP 进行网络质量测试，并自动更新 DNS 记录为最优 IP。

[English](./README_EN.md) | [简体中文](./README.md)

## ✨ 特性

- 🚀 使用 ITDOG 节点自动测试 Cloudflare IP 质量
- 📊 支持电信、联通、移动及海外多个区域的延迟测试
- 🔄 自动更新 DNS 记录（支持阿里云、DNSPod、华为云）
- ⚡ 智能 IP 质量评估和筛选系统
- 🔍 完整的测试日志和历史记录追踪
- 🤖 支持 GitHub Actions 自动化运行
- 📈 IP 历史数据分析和增量优化更新

## 🚀 快速开始

### GitHub Actions 配置

1. Fork 本仓库

2. 添加仓库密钥：
   - 进入仓库的 `Settings` > `Secrets and variables` > `Actions`
   - 根据你使用的 DNS 服务商添加对应的密钥：
```
# DNS服务商密钥
ALIYUN_KEY        # 阿里云 AccessKey ID
ALIYUN_SECRET     # 阿里云 AccessKey Secret
DNSPOD_ID         # DNSPod Secret ID
DNSPOD_KEY        # DNSPod Secret Key
HUAWEI_AK         # 华为云 Access Key
HUAWEI_SK         # 华为云 Secret Key

# 域名配置
DOMAIN            # 你的域名，例如：example.com
SUBDOMAIN         # 你的子域名，例如：cdn
```

3. 启用 GitHub Actions：
   - 进入仓库的 `Actions` 标签页
   - 启用 workflow
   - 测试会每5小时自动运行一次

### 本地部署

1. 克隆仓库：
```bash
git clone https://github.com/yourusername/Cloudflare-Preference-IP.git
cd Cloudflare-Preference-IP
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 修复 aliyunsdkcore：
```bash
# 进入 Python 包目录
cd .venv/lib/python3.12/site-packages/aliyunsdkcore

# 替换 [six.py](https://raw.githubusercontent.com/benjaminp/six/1.16.0/six.py) 文件到以下两个位置：
# - aliyunsdkcore/vendored/six.py
# - vendored/requests/packages/urllib3/packages/six.py
```

4. 更新配置文件
   - 配置 `config/settings.json`
   - 配置 `config/ip_ranges.json`

5. 运行测试：
```bash
python main.py
```

## ⚙️ 配置说明

### IP 范围配置 (config/ip_ranges.json)
```json
{
  "ip_ranges": [
    {
      "prefix": "104.16",    // IP前缀
      "start": 0,           // 起始范围
      "end": 255           // 结束范围
    }
  ],
  "skip_ips": [            // 跳过的IP列表
    "1.1.1.1",
    "1.0.0.1"
  ]
}
```

### 主配置文件 (config/settings.json)
```json
{
  "test_config": {
    "test_interval": 1,        // 测试间隔时间(秒)
    "sample_rate": 0.0002,     // 采样率
    "sample_size": 100,        // 采样数量
    "overseas_mode": true      // 是否测试境外线路
  },
  
  "dns": {
    "providers": {
      "aliyun": {
        "enabled": true,
        "access_key_id": "",    // 从环境变量 ALIYUN_KEY 获取
        "access_key_secret": "", // 从环境变量 ALIYUN_SECRET 获取
        "region": "cn-hangzhou"
      }
      // 其他DNS服务商配置类似
    },
    "max_records_per_line": 2,  // 每个线路保留的IP数量
    "default_ttl": 600         // DNS记录TTL值
  },
  
  {
  "domains": {
  "default": {
    "domain": "",              // 可选，默认从环境变量获取
    "subdomain": "",           // 可选，默认从环境变量获取
    "lines": ["CM", "CU", "CT", "AB"]
      }
    }
  }
}
```

## 🔄 IP 优选策略

工具通过多维度分析选择最优 IP：
- 延迟测试：测试 IP 对各运营商节点的响应时间
- 稳定性评估：分析 IP 的延迟波动情况
- 可用性监测：跟踪 IP 的连接成功率
- 历史表现：记录并分析 IP 30天内的表现
- 智能更新：
  - 保留表现稳定的优质 IP
  - 持续发现和引入新的优质 IP
  - 自动淘汰表现差的 IP

## 📊 测试结果

每次运行后可查看：
- `results/test_results_latest.json`: 最新测试数据
- `results/final_results_latest.json`: 最终分析结果
- `logs/`: 详细运行日志

## 🌟 测试节点

使用 ITDOG 提供的以下运营商节点：

- 中国电信：
  - 全国多个省份优质节点
  - 覆盖主要城市和地区

- 中国联通：
  - 全国范围的测试节点
  - 包括一二线城市

- 中国移动：
  - 覆盖全国的测速节点
  - 包括各省主要城市

- 海外节点（可选）：
  - 香港、新加坡、日本等地区

## 📃 许可证

[MIT 许可证](./LICENSE)

## 🤝 贡献

欢迎提交 Issues 和 Pull Requests！