# API Reference

> **WARNING:** This API reference is auto-generated from the OpenAPI specification
> but the generation tool has known issues with enum serialization and response
> schema references. Specifically, the generator produces incorrect TypeScript types
> for `oneOf` schemas and misses some `$ref` references in response bodies.
> These issues are documented in the generator's issue tracker but the fixes
> haven't been applied because the team that maintains the generator was disbanded
> in the 2023 reorg. The generated types are patched manually in the frontend
> service layer.
>
> The OpenAPI spec is located at `docs/openapi/v3.yaml`. This spec was migrated
> from Swagger 2.0 to OpenAPI 3.0 in Q1 2023. The migration was automated but
> some endpoint definitions were lost in translation. The missing endpoints are
> documented in the internal wiki under "OpenAPI Migration Missing Endpoints."
> If you encounter a 404 from an endpoint that should exist, check that list.
>
> TODO: Re-generate this reference from the current API spec and fix the
> generation tool issues. The generation is a manual step that involves
> running a Docker container with the spec generator. The Docker image is
> at `registry.internal.example.com/api-spec-generator:v3` but the registry
> requires authentication. The credentials are in the shared team vault.
> The vault path is `secret/team/api-spec-generator`.

## Base URL

All API endpoints are relative to:

```
https://api.example.com/v3
```

For development, use:

```
http://localhost:8080/api/v3
```

## Authentication

Most endpoints require authentication via Bearer token:

```
Authorization: Bearer <access_token>
```

Tokens are obtained from the `/auth/login` endpoint and expire after 1 hour.
Use the `/auth/refresh` endpoint with the refresh token to obtain a new
access token without requiring the user to re-authenticate.

### Rate Limiting

API requests are rate-limited per API key and per IP address. The rate limit
headers are included in all API responses:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests per window |
| `X-RateLimit-Remaining` | Remaining requests in current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |

Default rate limits:
- Authenticated: 100 requests per second
- Unauthenticated: 10 requests per second
- WebSocket: 1000 messages per second per connection

### Error Responses

All API errors follow a standard format:

```json
{
  "code": 4001,
  "message": "Invalid request parameters",
  "request_id": "req_abc123",
  "details": {
    "field": "symbol",
    "reason": "Unknown instrument symbol"
  }
}
```

Common error codes:

| Code | Description |
|------|-------------|
| 4001 | Invalid request |
| 4002 | Authentication required |
| 4003 | Insufficient permissions |
| 4004 | Resource not found |
| 4029 | Rate limit exceeded |
| 5001 | Internal server error |
| 5002 | Service unavailable |

---

## Market Data Endpoints

### GET /market/instruments

Returns a list of all tradeable instruments.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `type` | string | No | Filter by instrument type (stock, crypto, forex) |
| `exchange` | string | No | Filter by exchange |
| `status` | string | No | Filter by status (active, halted, delisted) |
| `search` | string | No | Search by symbol or name |
| `page` | integer | No | Page number (default: 1) |
| `per_page` | integer | No | Items per page (default: 50, max: 200) |

**Response:**

```json
{
  "instruments": [
    {
      "id": "btc-usd",
      "symbol": "BTC/USD",
      "name": "Bitcoin / US Dollar",
      "type": "crypto",
      "exchange": "internal",
      "currency": "USD",
      "base_currency": "BTC",
      "quote_currency": "USD",
      "tick_size": 0.01,
      "lot_size": 0.0001,
      "min_order_size": 0.001,
      "max_order_size": 1000,
      "price_precision": 2,
      "size_precision": 4,
      "status": "active"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 247,
    "total_pages": 5
  }
}
```

### GET /market/instruments/{id}

Returns details for a specific instrument.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Instrument ID |

### GET /market/orderbook

Returns the current order book for an instrument.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Instrument symbol |
| `depth` | integer | No | Number of price levels (default: 50, max: 100) |
| `aggregation` | number | No | Price aggregation level |

**Response:**

```json
{
  "symbol": "BTC/USD",
  "bids": [
    {"price": 50000.00, "size": 1.5, "total": 1.5, "order_count": 3}
  ],
  "asks": [
    {"price": 50001.00, "size": 2.0, "total": 2.0, "order_count": 5}
  ],
  "timestamp": 1704070800000,
  "sequence": 12345678
}
```

### GET /market/ticker

Returns the current ticker for an instrument.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Instrument symbol |

**Response:**

```json
{
  "symbol": "BTC/USD",
  "price": 50000.00,
  "bid": 49999.00,
  "ask": 50001.00,
  "volume_24h": 12500.5,
  "change_24h": 250.00,
  "change_pct_24h": 0.50,
  "high_24h": 50200.00,
  "low_24h": 49700.00,
  "timestamp": 1704070800000
}
```

### GET /market/candles

Returns historical OHLCV candle data.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Instrument symbol |
| `timeframe` | string | Yes | Candle interval (1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w) |
| `from` | integer | No | Start timestamp (milliseconds) |
| `to` | integer | No | End timestamp (milliseconds) |
| `limit` | integer | No | Maximum candles to return (default: 500, max: 5000) |

### GET /market/trades

Returns recent trades for an instrument.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | Yes | Instrument symbol |
| `limit` | integer | No | Maximum trades (default: 100, max: 1000) |
| `since` | integer | No | Return trades after this timestamp |

### GET /market/news

Returns market news and announcements.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `symbol` | string | No | Filter by instrument |
| `limit` | integer | No | Maximum articles (default: 20) |
| `since` | integer | No | Return articles after this timestamp |

---

## Order Management Endpoints

### POST /orders

Place a new order.

**Request Body:**

```json
{
  "instrument_id": "btc-usd",
  "side": "buy",
  "type": "limit",
  "price": 50000.00,
  "quantity": 0.1,
  "time_in_force": "gtc",
  "client_order_id": "my-order-123"
}
```

**Response:**

```json
{
  "order_id": "ord_abc123",
  "status": "new",
  "created_at": "2024-01-01T00:00:00Z",
  "client_order_id": "my-order-123"
}
```

### GET /orders

Returns orders for the authenticated user.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `status` | string | No | Filter by status |
| `instrument` | string | No | Filter by instrument |
| `side` | string | No | Filter by side (buy, sell) |
| `from` | string | No | Start date |
| `to` | string | No | End date |
| `page` | integer | No | Page number |
| `per_page` | integer | No | Items per page |

### GET /orders/{id}

Returns details for a specific order.

### DELETE /orders/{id}

Cancel an open order.

---

## Account Endpoints

### GET /account/summary

Returns account summary including balances and buying power.

### GET /account/transactions

Returns transaction history.

### GET /positions

Returns open positions.

### GET /positions/{instrument_id}

Returns position details for a specific instrument.

---

## Authentication Endpoints

### POST /auth/login

Authenticate with email and password.

**Request Body:**

```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "mfa_code": "123456"
}
```

### POST /auth/register

Create a new account.

### POST /auth/refresh

Refresh an expired access token.

### POST /auth/logout

Invalidate the current session.

---

## WebSocket API

### Connection

```
wss://api.example.com/ws
```

### Authentication

Send an authentication message after connecting:

```json
{
  "type": "auth",
  "token": "<access_token>"
}
```

### Subscribing to Market Data

```json
{
  "type": "subscribe",
  "channel": "market.ticker",
  "symbol": "BTC/USD"
}
```

### Available Channels

| Channel | Description | Update Frequency |
|---------|-------------|-----------------|
| `market.ticker` | Real-time ticker updates | 100ms |
| `market.orderbook` | Real-time order book updates | 100ms |
| `market.trades` | Real-time trade executions | 100ms |
| `market.candles` | Historical candle data updates | 1s |

## JSONL Output Format

The API supports JSONL (JSON Lines) format for streaming data responses. JSONL is a text format where each line is a valid JSON object, making it ideal for streaming applications and large datasets.

### Requesting JSONL Format

Add the `format=jsonl` query parameter to any endpoint that supports streaming or large datasets:

```
GET /market/trades?symbol=BTC/USD&limit=1000&format=jsonl
```

### JSONL Response Example

Instead of a single JSON array, the response will be a stream of JSON objects, one per line:

```json
{"symbol":"BTC/USD","id":"trade_12345","price":50000.00,"quantity":0.1,"side":"buy","timestamp":1704070800000}
{"symbol":"BTC/USD","id":"trade_12346","price":49999.50,"quantity":0.05,"side":"sell","timestamp":1704070801000}
{"symbol":"BTC/USD","id":"trade_12347","price":50000.50,"quantity":0.2,"side":"buy","timestamp":1704070802000}
```

### WebSocket JSONL Streaming

For WebSocket connections, you can request JSONL format by including it in the subscription message:

```json
{
  "type": "subscribe",
  "channel": "market.trades",
  "symbol": "BTC/USD",
  "format": "jsonl"
}
```

Each message received will be a separate JSON object on its own line.

### Advantages of JSONL Format

- **Memory efficient**: Processes one line at a time without loading entire dataset into memory
- **Streamable**: Can be processed as it arrives, ideal for real-time applications
- **Backwards compatible**: Easy to parse with existing JSON libraries
- **Human readable**: Each line is a complete JSON object that can be examined individually

### Consuming JSONL Data

Example Python code to consume JSONL data:

```python
import json

for line in response.iter_lines():
    if line:
        trade = json.loads(line)
        print(f"Trade: {trade['symbol']} at {trade['price']}")
```

Example Node.js code:

```javascript
const readline = require('readline');

const rl = readline.createInterface({
  input: response,
  crlfDelay: Infinity
});

rl.on('line', (line) => {
  const trade = JSON.parse(line);
  console.log(`Trade: ${trade.symbol} at ${trade.price}`);
});
```
| `market.orderbook` | Order book snapshots | 100ms |
| `market.trades` | Recent trades | Real-time |
| `market.candles` | Candle updates (1m) | 1 minute |
| `account.orders` | User's order updates | Real-time |
| `account.positions` | User's position updates | Real-time |
| `account.notifications` | User notifications | Real-time |
