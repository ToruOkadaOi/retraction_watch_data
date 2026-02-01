# Retraction Watch API

A FastAPI-based REST API for querying the Retraction Watch database. This API provides programmatic access to retraction data with filtering, pagination, and comprehensive documentation.

## Features

- 🔍 **Query retractions** by author, year, and journal
- 📄 **Get detailed information** about specific retractions
- 👥 **List authors** with retraction counts
- 📚 **List journals** with retraction statistics
- 📖 **Interactive Swagger documentation** (OpenAPI 3.0)
- 🐳 **Docker support** for easy deployment
- ⚡ **Fast queries** with SQLite database backend

## Quick Start

### Prerequisites

- Python 3.11 or higher
- pip

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database (load CSV data):
```bash
python -m api.database
```

3. Run the API server:
```bash
uvicorn api.main:app --reload
```

The API will be available at `http://localhost:8000`

### Using Docker

Build and run with Docker:

```bash
docker build -t retraction-api .
docker run -p 8000:8000 retraction-api
```

## API Documentation

Once the server is running, access the interactive API documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

## API Endpoints

### GET /retractions

Query all retractions with optional filters and pagination.

**Query Parameters:**
- `author` (optional): Filter by author name (partial match, case-insensitive)
- `year` (optional): Filter by retraction year (e.g., 2021)
- `journal` (optional): Filter by journal name (partial match, case-insensitive)
- `page` (optional): Page number (default: 1)
- `page_size` (optional): Items per page (default: 20, max: 100)

**Example:**
```bash
curl "http://localhost:8000/retractions?author=Smith&year=2021&page=1&page_size=10"
```

### GET /retractions/{id}

Retrieve detailed information about a specific retraction by its Record ID.

**Example:**
```bash
curl "http://localhost:8000/retractions/69157"
```

### GET /authors

Get a list of all authors with their retraction counts, sorted by count.

**Query Parameters:**
- `limit` (optional): Maximum number of authors to return (default: 100, max: 1000)

**Example:**
```bash
curl "http://localhost:8000/authors?limit=50"
```

### GET /journals

Get a list of all journals with their retraction counts, sorted by count.

**Query Parameters:**
- `limit` (optional): Maximum number of journals to return (default: 100, max: 1000)

**Example:**
```bash
curl "http://localhost:8000/journals?limit=50"
```

## Data Schema

The API uses the Retraction Watch database schema with the following main fields:

- `record_id`: Unique identifier from Retraction Watch
- `title`: Title of the retracted content
- `author`: List of authors (semicolon-separated)
- `journal`: Journal or publication source
- `retraction_date`: Date of retraction
- `original_paper_date`: Original publication date
- `retraction_nature`: Type (Retraction, Correction, Expression of Concern)
- `reason`: Reasons for retraction (semicolon-separated)
- And many more fields...

See the Swagger documentation for complete field descriptions.

## Development

### Project Structure

```
.
├── api/
│   ├── __init__.py
│   ├── main.py          # FastAPI application and endpoints
│   ├── models.py        # Pydantic models for validation
│   └── database.py      # Database setup and utilities
├── retraction_watch.csv # Source data
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
└── API_README.md       # This file
```

### Running Tests

The API can be tested interactively using the Swagger UI at `/docs`, or programmatically:

```python
import requests

# Test retractions endpoint
response = requests.get("http://localhost:8000/retractions?year=2025&page_size=5")
print(response.json())

# Test specific retraction
response = requests.get("http://localhost:8000/retractions/69157")
print(response.json())
```

## OpenAPI Compliance

This API fully complies with OpenAPI 3.0 standards:

- ✅ Complete schema definitions for all request/response models
- ✅ Detailed endpoint descriptions and parameter documentation
- ✅ Response status codes and error handling
- ✅ Type validation and constraints
- ✅ Example values and use cases

## Performance Considerations

- The database is loaded into SQLite for fast queries
- Indexes are created on commonly filtered fields (author, journal, date)
- Pagination limits prevent excessive data transfer
- Connection pooling is handled by SQLAlchemy

## Data Source

Data is sourced from the Retraction Watch database, maintained by Crossref. The database contains retractions gathered from publisher websites and is updated regularly.

For more information, visit: https://retractionwatch.com/

## License

The API code is open source. The data is provided by Retraction Watch/Crossref - please refer to their licensing terms for data usage.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.
