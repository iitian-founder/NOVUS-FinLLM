from langchain_core.tools import tool
import math

@tool
def calculate_cagr(beginning_value: float, ending_value: float, years: int) -> float:
    """
    Calculate the Compound Annual Growth Rate (CAGR).
    
    Args:
        beginning_value: Starting value (e.g. past revenue).
        ending_value: Ending value (e.g. current revenue).
        years: Number of years between beginning and ending.
    """
    if beginning_value <= 0 or ending_value < 0 or years <= 0:
        return 0.0
    return (math.pow((ending_value / beginning_value), (1.0 / years)) - 1.0) * 100.0

@tool
def project_future_value(current_value: float, growth_rate_percentage: float, years_out: int) -> float:
    """
    Project a future value using a steady growth rate.
    
    Args:
        current_value: The base value to project from.
        growth_rate_percentage: The yearly growth rate as a percentage (e.g. 15.5).
        years_out: Number of years into the future.
    """
    if years_out <= 0:
        return current_value
    
    rate = growth_rate_percentage / 100.0
    return current_value * math.pow((1.0 + rate), years_out)

@tool
def calculate_margin(metric_value: float, revenue_value: float) -> float:
    """
    Calculate margin as a percentage of revenue.
    """
    if revenue_value <= 0:
        return 0.0
    return (metric_value / revenue_value) * 100.0
