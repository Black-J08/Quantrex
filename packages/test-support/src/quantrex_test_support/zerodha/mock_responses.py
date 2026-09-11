"""Test fixtures for Zerodha provider testing."""

# Sample instrument master CSV (compact format, mirrors Zerodha's live schema:
# https://api.kite.trade/instruments)
# Columns: instrument_token, exchange_token, tradingsymbol, name, last_price, expiry, strike, tick_size, lot_size, instrument_type, segment, exchange
MOCK_INSTRUMENT_MASTER_CSV = """instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,segment,exchange
408065,1594,INFY,INFOSYS,0,,,0.05,1,EQ,NSE,NSE
5720322,22345,NIFTY24JANFUT,,78.0,2024-01-25,,0.05,75,FUT,NFO,NFO
5720578,22346,NIFTY24JAN25000CE,,23.0,2024-01-25,25000,0.05,75,CE,NFO,NFO
5720579,22347,NIFTY24JAN25000PE,,23.0,2024-01-25,25000,0.05,75,PE,NFO,NFO
5633,1594,RELIANCE,RELIANCE INDUSTRIES,0,,,0.05,1,EQ,NSE,NSE
12345,12345,COPPER24JANFUT,,7800.0,2024-01-19,,1,1,FUT,MCX,MCX
"""

# Sample historical data response (minute interval).
# ``candles`` is an array of [timestamp, open, high, low, close, volume] arrays.
# Timestamp is ISO 8601 with timezone offset (IST = UTC+05:30).
# The first candle is 2024-01-01 09:15:00 IST.
MOCK_HISTORICAL_RESPONSE_MINUTE = {
    "status": "success",
    "data": {
        "candles": [
            ["2024-01-01T09:15:00+0530", 2500.0, 2502.0, 2499.0, 2501.0, 1000],
            ["2024-01-01T09:16:00+0530", 2501.0, 2503.0, 2500.0, 2502.0, 1500],
            ["2024-01-01T09:17:00+0530", 2502.0, 2504.0, 2501.0, 2501.5, 1200],
            ["2024-01-01T09:18:00+0530", 2501.5, 2503.5, 2500.5, 2503.0, 1800],
            ["2024-01-01T09:19:00+0530", 2503.0, 2505.0, 2502.0, 2504.0, 2000],
        ]
    }
}

# Sample historical data response (day interval).
# The first candle is 2024-01-01 00:00:00 IST (midnight of trading day).
MOCK_HISTORICAL_RESPONSE_DAY = {
    "status": "success",
    "data": {
        "candles": [
            ["2024-01-01T00:00:00+0530", 2500.0, 2520.0, 2490.0, 2510.0, 100000],
            ["2024-01-02T00:00:00+0530", 2510.0, 2525.0, 2505.0, 2520.0, 150000],
            ["2024-01-03T00:00:00+0530", 2520.0, 2535.0, 2510.0, 2515.0, 120000],
            ["2024-01-04T00:00:00+0530", 2515.0, 2525.0, 2500.0, 2530.0, 180000],
            ["2024-01-05T00:00:00+0530", 2530.0, 2540.0, 2520.0, 2535.0, 200000],
        ]
    }
}

# Sample historical data response with OI (open interest).
# Each candle has 7 elements: [timestamp, open, high, low, close, volume, oi]
MOCK_HISTORICAL_RESPONSE_WITH_OI = {
    "status": "success",
    "data": {
        "candles": [
            ["2024-01-01T09:15:00+0530", 2500.0, 2502.0, 2499.0, 2501.0, 1000, 50000],
            ["2024-01-01T09:16:00+0530", 2501.0, 2503.0, 2500.0, 2502.0, 1500, 50100],
            ["2024-01-01T09:17:00+0530", 2502.0, 2504.0, 2501.0, 2501.5, 1200, 50200],
        ]
    }
}

# Sample auth success response
MOCK_AUTH_SUCCESS_RESPONSE = {
    "status": "success",
    "data": {
        "user_type": "individual",
        "email": "test@example.com",
        "user_name": "Test User",
        "user_shortname": "Test",
        "broker": "ZERODHA",
        "exchanges": ["NSE", "NFO", "BSE", "BFO", "CDS", "MCX"],
        "products": ["CNC", "NRML", "MIS"],
        "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
        "api_key": "test_api_key",
        "access_token": "test_access_token_12345",
        "public_token": "public_token_123",
        "login_time": "2024-01-01 10:00:00",
    }
}

# Sample auth error response (TokenException)
MOCK_AUTH_ERROR_RESPONSE = {
    "status": "error",
    "message": "TokenException: Token is invalid or has expired",
    "error_type": "TokenException"
}

# Sample rate limit error response
MOCK_RATE_LIMIT_ERROR_RESPONSE = {
    "status": "error",
    "message": "Rate limit exceeded. Please retry after 1 second.",
    "error_type": "RateLimitException"
}

# Sample invalid parameter error response
MOCK_INVALID_PARAM_ERROR_RESPONSE = {
    "status": "error",
    "message": "InputException: Invalid instrument_token",
    "error_type": "InputException"
}

# Sample empty data response
MOCK_EMPTY_DATA_RESPONSE = {
    "status": "success",
    "data": {
        "candles": []
    }
}

# Sample user profile response (for token validation)
MOCK_USER_PROFILE_RESPONSE = {
    "status": "success",
    "data": {
        "user_id": "AB1234",
        "user_type": "individual",
        "email": "test@example.com",
        "user_name": "Test User",
        "user_shortname": "Test",
        "broker": "ZERODHA",
        "exchanges": ["NSE", "NFO", "BSE", "BFO", "CDS", "MCX"],
        "products": ["CNC", "NRML", "MIS"],
        "order_types": ["MARKET", "LIMIT", "SL", "SL-M"],
    }
}