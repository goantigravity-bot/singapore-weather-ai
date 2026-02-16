# NEA数据获取脚本改进计划

## 📋 当前问题

### 硬编码日期配置

**当前代码** (`fetch_and_process_gov_data.py` 第11-23行):
```python
FETCH_CONFIG = [
    datetime.date(2026, 1, 1),
    {'start': datetime.date(2026, 1, 14), 'end': datetime.date(2026, 1, 15)},
    {'start': datetime.date(2026, 1, 17), 'end': datetime.date(2026, 1, 20)},
]
```

**问题**:
1. ❌ 日期硬编码，每次都需要手动修改
2. ❌ 不支持增量更新
3. ❌ 不支持从环境变量或命令行参数读取
4. ❌ 会重复下载已有数据

---

## 🎯 改进方案

### 方案1: 支持命令行参数（推荐 ⭐）

**实施代码**:
```python
import argparse
from datetime import datetime, timedelta, date

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='获取NEA天气数据')
    
    parser.add_argument(
        '--start-date',
        type=str,
        help='开始日期 (YYYY-MM-DD)，默认为昨天'
    )
    
    parser.add_argument(
        '--end-date',
        type=str,
        help='结束日期 (YYYY-MM-DD)，默认为今天'
    )
    
    parser.add_argument(
        '--days',
        type=int,
        help='获取最近N天的数据'
    )
    
    parser.add_argument(
        '--mode',
        choices=['incremental', 'full', 'range'],
        default='incremental',
        help='模式: incremental(增量), full(全量), range(指定范围)'
    )
    
    return parser.parse_args()

def determine_date_range(args):
    """根据参数确定日期范围"""
    today = date.today()
    
    if args.mode == 'incremental':
        # 增量模式: 检查现有数据，只下载新数据
        if os.path.exists(OUTPUT_FILE):
            df_existing = pd.read_csv(OUTPUT_FILE)
            df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'])
            last_date = df_existing['timestamp'].max().date()
            start_date = last_date + timedelta(days=1)
        else:
            # 如果没有现有数据，下载最近30天
            start_date = today - timedelta(days=30)
        end_date = today
        
    elif args.mode == 'full':
        # 全量模式: 下载所有配置的日期
        # 保留原有的FETCH_CONFIG逻辑
        return None  # 使用FETCH_CONFIG
        
    elif args.mode == 'range':
        # 范围模式: 使用指定的日期范围
        if args.start_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        else:
            start_date = today - timedelta(days=7)
            
        if args.end_date:
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        else:
            end_date = today
    
    # 如果指定了days参数，覆盖其他设置
    if args.days:
        end_date = today
        start_date = today - timedelta(days=args.days)
    
    return start_date, end_date

def main():
    args = parse_arguments()
    
    # 确定日期范围
    date_range = determine_date_range(args)
    
    if date_range is None:
        # 使用FETCH_CONFIG（向后兼容）
        dates_to_process = set()
        for item in FETCH_CONFIG:
            if isinstance(item, date):
                dates_to_process.add(item)
            elif isinstance(item, dict) and 'start' in item and 'end' in item:
                current = item['start']
                end = item['end']
                while current <= end:
                    dates_to_process.add(current)
                    current += timedelta(days=1)
    else:
        # 使用计算的日期范围
        start_date, end_date = date_range
        print(f"日期范围: {start_date} 至 {end_date}")
        
        dates_to_process = set()
        current = start_date
        while current <= end_date:
            dates_to_process.add(current)
            current += timedelta(days=1)
    
    # ... 继续原有的处理逻辑
```

**使用示例**:
```bash
# 增量模式（默认）- 只下载新数据
python3 fetch_and_process_gov_data.py

# 下载最近7天
python3 fetch_and_process_gov_data.py --days 7

# 指定日期范围
python3 fetch_and_process_gov_data.py --mode range --start-date 2026-01-20 --end-date 2026-01-25

# 全量模式（使用FETCH_CONFIG）
python3 fetch_and_process_gov_data.py --mode full
```

---

### 方案2: 支持环境变量

**实施代码**:
```python
# 从环境变量读取日期
FETCH_START_DATE = os.environ.get('FETCH_START_DATE')
FETCH_END_DATE = os.environ.get('FETCH_END_DATE')

if FETCH_START_DATE and FETCH_END_DATE:
    start_date = datetime.strptime(FETCH_START_DATE, '%Y-%m-%d').date()
    end_date = datetime.strptime(FETCH_END_DATE, '%Y-%m-%d').date()
    
    FETCH_CONFIG = [
        {'start': start_date, 'end': end_date}
    ]
```

**使用示例**:
```bash
export FETCH_START_DATE="2026-01-20"
export FETCH_END_DATE="2026-01-25"
python3 fetch_and_process_gov_data.py
```

---

### 方案3: 智能增量更新（推荐 ⭐⭐）

**实施代码**:
```python
def get_incremental_dates():
    """智能确定需要下载的日期"""
    
    # 1. 检查现有数据
    if os.path.exists(OUTPUT_FILE):
        try:
            df_existing = pd.read_csv(OUTPUT_FILE)
            df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'])
            
            # 获取最后一条记录的日期
            last_timestamp = df_existing['timestamp'].max()
            last_date = last_timestamp.date()
            
            print(f"现有数据最后日期: {last_date}")
            
            # 从最后日期的下一天开始
            start_date = last_date + timedelta(days=1)
            end_date = date.today()
            
            if start_date > end_date:
                print("数据已是最新，无需下载")
                return []
            
            print(f"增量下载: {start_date} 至 {end_date}")
            
        except Exception as e:
            print(f"读取现有数据失败: {e}")
            print("将下载最近30天数据")
            start_date = date.today() - timedelta(days=30)
            end_date = date.today()
    else:
        # 首次运行，下载最近30天
        print("首次运行，下载最近30天数据")
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
    
    # 生成日期列表
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    
    return dates

def merge_with_existing_data(new_df):
    """合并新数据和现有数据"""
    if os.path.exists(OUTPUT_FILE):
        try:
            df_existing = pd.read_csv(OUTPUT_FILE)
            df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'])
            
            # 合并
            df_combined = pd.concat([df_existing, new_df], ignore_index=True)
            
            # 去重（基于timestamp和sensor_id）
            df_combined = df_combined.drop_duplicates(
                subset=['timestamp', 'sensor_id'],
                keep='last'
            )
            
            # 排序
            df_combined = df_combined.sort_values(['sensor_id', 'timestamp'])
            
            print(f"合并数据: {len(df_existing)} + {len(new_df)} = {len(df_combined)} 条记录")
            
            return df_combined
            
        except Exception as e:
            print(f"合并失败: {e}，使用新数据")
            return new_df
    else:
        return new_df
```

---

## 🔧 完整改进版本

### 新的 `fetch_and_process_gov_data.py`

关键改进:
1. ✅ 支持命令行参数
2. ✅ 支持环境变量
3. ✅ 智能增量更新
4. ✅ 自动合并数据
5. ✅ 向后兼容（保留FETCH_CONFIG）

---

## 📊 使用场景

### 场景1: 自动化训练流程（推荐）

```python
# auto_train_pipeline.py 中的调用
def step_2_download_sensor_data(self):
    # 使用增量模式，自动检测需要下载的日期
    cmd = ["python3", "fetch_and_process_gov_data.py", "--mode", "incremental"]
    return self.run_command(cmd, "下载传感器数据", timeout=1800)
```

### 场景2: 手动补充数据

```bash
# 补充特定日期范围的数据
python3 fetch_and_process_gov_data.py --mode range \
    --start-date 2026-01-15 \
    --end-date 2026-01-20
```

### 场景3: 初始化数据

```bash
# 首次运行，下载最近30天
python3 fetch_and_process_gov_data.py --days 30
```

---

## 📝 实施步骤

1. **备份现有脚本**
   ```bash
   cp fetch_and_process_gov_data.py fetch_and_process_gov_data.py.bak
   ```

2. **修改脚本**
   - 添加命令行参数解析
   - 添加增量更新逻辑
   - 添加数据合并功能

3. **测试**
   ```bash
   # 测试增量模式
   python3 fetch_and_process_gov_data.py --mode incremental
   
   # 测试范围模式
   python3 fetch_and_process_gov_data.py --mode range --days 7
   ```

4. **更新自动化流程**
   - 修改 `auto_train_pipeline.py`
   - 使用新的命令行参数

---

## ⚠️ 注意事项

1. **API限制**
   - NEA API可能有速率限制
   - 建议每次请求间隔0.5-1秒

2. **数据完整性**
   - 合并数据时检查重复
   - 验证时间戳连续性

3. **错误处理**
   - 网络错误时重试
   - 部分日期失败不影响其他日期

---

**创建时间**: 2026-01-25 22:01  
**状态**: 待实施  
**优先级**: 高  
**依赖**: 与训练优化计划一起实施
