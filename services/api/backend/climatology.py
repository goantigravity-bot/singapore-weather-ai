"""
新加坡气候均值查找表 — 作为无实时传感器数据时的 fallback。

数据来源: Meteorological Service Singapore (MSS) 历史月度统计。
按月和时段（昼 06-18 / 夜 18-06）提供均值，足以让模型产生
合理输出，而非因缺数据直接失败。
"""

import logging

logger = logging.getLogger(__name__)

# 按月份的气候均值 (temperature °C, humidity %, pm25 μg/m³)
# 新加坡全年温差小，主要差异在降雨量和湿度
_MONTHLY_CLIMATE = {
    1:  {"temp_day": 30.5, "temp_night": 25.0, "humidity_day": 75, "humidity_night": 88, "pm25": 15},
    2:  {"temp_day": 31.0, "temp_night": 25.2, "humidity_day": 72, "humidity_night": 86, "pm25": 16},
    3:  {"temp_day": 31.5, "temp_night": 25.5, "humidity_day": 73, "humidity_night": 87, "pm25": 18},
    4:  {"temp_day": 31.5, "temp_night": 25.8, "humidity_day": 75, "humidity_night": 88, "pm25": 18},
    5:  {"temp_day": 31.5, "temp_night": 26.0, "humidity_day": 76, "humidity_night": 88, "pm25": 17},
    6:  {"temp_day": 31.5, "temp_night": 26.0, "humidity_day": 75, "humidity_night": 87, "pm25": 16},
    7:  {"temp_day": 31.0, "temp_night": 25.8, "humidity_day": 75, "humidity_night": 87, "pm25": 15},
    8:  {"temp_day": 31.0, "temp_night": 25.8, "humidity_day": 75, "humidity_night": 87, "pm25": 16},
    9:  {"temp_day": 31.0, "temp_night": 25.5, "humidity_day": 75, "humidity_night": 88, "pm25": 20},
    10: {"temp_day": 31.0, "temp_night": 25.5, "humidity_day": 76, "humidity_night": 89, "pm25": 22},
    11: {"temp_day": 30.5, "temp_night": 25.2, "humidity_day": 78, "humidity_night": 90, "pm25": 19},
    12: {"temp_day": 30.0, "temp_night": 25.0, "humidity_day": 79, "humidity_night": 90, "pm25": 16},
}


def get_climatology(month: int, hour: int) -> dict:
    """
    返回指定月份和小时的气候均值。

    Returns:
        {"temperature": float, "humidity": float, "pm25": float, "rainfall": 0.0}
    """
    climate = _MONTHLY_CLIMATE.get(month, _MONTHLY_CLIMATE[1])
    is_day = 6 <= hour < 18

    return {
        "temperature": climate["temp_day"] if is_day else climate["temp_night"],
        "humidity": climate["humidity_day"] if is_day else climate["humidity_night"],
        "pm25": climate["pm25"],
        "rainfall": 0.0,  # 气候均值不预测降雨，交给模型判断
    }
