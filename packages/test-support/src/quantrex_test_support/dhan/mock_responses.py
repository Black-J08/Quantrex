"""Test fixtures for Dhan provider testing."""

# Sample instrument master CSV (compact format, mirrors Dhan's live schema:
# https://images.dhan.co/api-data/api-scrip-master.csv).
# Columns used by the parser: SEM_EXM_EXCH_ID, SEM_SEGMENT, SEM_SMST_SECURITY_ID,
# SEM_TRADING_SYMBOL. Other columns are preserved for downstream consumers.
MOCK_INSTRUMENT_MASTER_CSV = """SEM_EXM_EXCH_ID,SEM_SEGMENT,SEM_SMST_SECURITY_ID,SEM_INSTRUMENT_NAME,SEM_EXPIRY_CODE,SEM_TRADING_SYMBOL,SEM_LOT_UNITS,SEM_CUSTOM_SYMBOL,SEM_EXPIRY_DATE,SEM_STRIKE_PRICE,SEM_OPTION_TYPE,SEM_TICK_SIZE,SEM_EXPIRY_FLAG,SEM_EXCH_INSTRUMENT_TYPE,SEM_SERIES,SM_SYMBOL_NAME
NSE,E,1333,EQUITY,0,RELIANCE,1.0,RELIANCE,,0,XX,0.01,NA,ES,EQ,RELIANCE Industries Ltd
NSE,E,11536,EQUITY,0,TCS,1.0,TCS,,0,XX,0.01,NA,ES,EQ,TCS Ltd
NSE,E,2885,EQUITY,0,HDFCBANK,1.0,HDFCBANK,,0,XX,0.01,NA,ES,EQ,HDFC Bank Ltd
NSE,E,3456,EQUITY,0,ICICIBANK,1.0,ICICIBANK,,0,XX,0.01,NA,ES,EQ,ICICI Bank Ltd
NSE,E,11630,EQUITY,0,INFY,1.0,INFY,,0,XX,0.01,NA,ES,EQ,Infosys Ltd
NSE,D,1333,FUTSTK,1,RELIANCE24JANFUT,250,RELIANCE24JANFUT,2024-01-25,0,XX,0.01,M,FUTSTK,,RELIANCE Industries Ltd
NSE,D,1333,OPTSTK,1,RELIANCE24JAN2500CE,250,RELIANCE24JAN2500CE,2024-01-25,2500,CE,0.01,M,OPTSTK,,RELIANCE Industries Ltd
NSE,D,1333,OPTSTK,1,RELIANCE24JAN2500PE,250,RELIANCE24JAN2500PE,2024-01-25,2500,PE,0.01,M,OPTSTK,,RELIANCE Industries Ltd
BSE,E,500325,EQUITY,0,RELIANCE,1.0,RELIANCE,,0,XX,0.01,NA,ES,EQ,RELIANCE Industries Ltd
MCX,M,12345,FUTCOM,0,COPPER24JANFUT,1000,COPPER24JANFUT,2024-01-19,0,XX,0.05,M,FUTCOM,,Copper Futures
"""

# Sample daily historical data response
MOCK_DAILY_HISTORICAL_RESPONSE = {
    "open": [2500.0, 2510.0, 2520.0, 2515.0, 2530.0],
    "high": [2520.0, 2525.0, 2535.0, 2525.0, 2540.0],
    "low": [2490.0, 2505.0, 2510.0, 2500.0, 2520.0],
    "close": [2510.0, 2520.0, 2515.0, 2530.0, 2535.0],
    "volume": [100000, 150000, 120000, 180000, 200000],
    "timestamp": [1704067200, 1704153600, 1704240000, 1704326400, 1704412800],  # 2024-01-01 to 2024-01-05
    "open_interest": [50000, 55000, 52000, 58000, 60000],
}

# Sample intraday historical data response (1-minute)
MOCK_INTRADAY_HISTORICAL_RESPONSE = {
    "open": [2500.0, 2501.0, 2502.0, 2501.5, 2503.0],
    "high": [2502.0, 2503.0, 2504.0, 2503.5, 2505.0],
    "low": [2499.0, 2500.0, 2501.0, 2500.5, 2502.0],
    "close": [2501.0, 2502.0, 2501.5, 2503.0, 2504.0],
    "volume": [1000, 1500, 1200, 1800, 2000],
    "timestamp": [1704093300, 1704093360, 1704093420, 1704093480, 1704093540],  # 2024-01-01 09:15 to 09:19 IST
    "open_interest": [50000, 50100, 50200, 50150, 50300],
}

# Sample error responses
MOCK_AUTH_ERROR_RESPONSE = {
    "status": "failure",
    "errorType": "AUTHENTICATION_ERROR",
    "errorCode": "AE001",
    "errorMessage": "Invalid access token"
}

MOCK_RATE_LIMIT_ERROR_RESPONSE = {
    "status": "failure",
    "errorType": "RATE_LIMIT_ERROR",
    "errorCode": "RL001",
    "errorMessage": "Too many requests. Please retry after 1 second."
}

MOCK_INVALID_PARAM_ERROR_RESPONSE = {
    "status": "failure",
    "errorType": "INVALID_PARAMETER",
    "errorCode": "813",
    "errorMessage": "Invalid SecurityId"
}

MOCK_EMPTY_DATA_RESPONSE = {
    "open": [],
    "high": [],
    "low": [],
    "close": [],
    "volume": [],
    "timestamp": [],
    "open_interest": [],
}