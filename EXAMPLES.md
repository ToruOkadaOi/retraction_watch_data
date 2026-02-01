# API Usage Examples

This document provides practical examples of using the Retraction Watch API.

## Prerequisites

Start the API server:
```bash
./start_api.sh
# or
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Example Requests

### 1. Get API Information

```bash
curl http://localhost:8000/
```

**Response:**
```json
{
    "message": "Welcome to the Retraction Watch API",
    "version": "1.0.0",
    "docs_url": "/docs",
    "openapi_url": "/openapi.json",
    "endpoints": {
        "retractions": "/retractions",
        "retraction_by_id": "/retractions/{id}",
        "authors": "/authors",
        "journals": "/journals"
    }
}
```

### 2. Query Retractions (Basic)

Get the first 10 retractions:

```bash
curl "http://localhost:8000/retractions?page=1&page_size=10"
```

**Response:**
```json
{
    "total": 68489,
    "page": 1,
    "page_size": 10,
    "retractions": [
        {
            "record_id": 69157,
            "title": "Process of mechanical processing of cylindrical long parts...",
            "journal": "E3S Web of Conferences",
            "author": "Shuhrat Fayzimatov;Yunusali Khusanov;...",
            "retraction_date": "1/6/2025 0:00",
            "retraction_nature": "Retraction",
            ...
        },
        ...
    ]
}
```

### 3. Filter by Author

Find all retractions by a specific author:

```bash
curl "http://localhost:8000/retractions?author=Joachim+Boldt&page_size=5"
```

**Response:**
```json
{
    "total": 235,
    "page": 1,
    "page_size": 5,
    "retractions": [...]
}
```

### 4. Filter by Year

Get retractions from 2025:

```bash
curl "http://localhost:8000/retractions?year=2025&page=1&page_size=20"
```

**Response:**
```json
{
    "total": 4636,
    "page": 1,
    "page_size": 20,
    "retractions": [...]
}
```

### 5. Filter by Journal

Find retractions from Nature journals:

```bash
curl "http://localhost:8000/retractions?journal=Nature&page_size=10"
```

**Response:**
```json
{
    "total": 486,
    "page": 1,
    "page_size": 10,
    "retractions": [...]
}
```

### 6. Combine Multiple Filters

Find retractions from a specific author in a specific journal:

```bash
curl "http://localhost:8000/retractions?author=Smith&journal=PLoS&year=2021&page_size=10"
```

### 7. Get Specific Retraction

Retrieve details for a specific retraction by its Record ID:

```bash
curl "http://localhost:8000/retractions/69157"
```

**Response:**
```json
{
    "record_id": 69157,
    "title": "Process of mechanical processing of cylindrical long parts and problems arising in the process",
    "subject": "(PHY) Engineering - Mechanical;",
    "institution": "Fergana Polytechnic Institute, 150107, Fergana street 86, Fergana, Uzbekistan;",
    "journal": "E3S Web of Conferences",
    "publisher": "EDP Sciences",
    "country": "Uzbekistan",
    "author": "Shuhrat Fayzimatov;Yunusali Khusanov;Abdukaxxor Omonov;Behzod Matkarimov;Shokhrukh Sadirov;Otabek Yusufjonov;Temur Turgunboev",
    "urls": null,
    "article_type": "Conference Abstract/Paper;",
    "retraction_date": "1/6/2025 0:00",
    "retraction_doi": "10.1051/e3sconf/202453800001",
    "retraction_pubmed_id": "0.0",
    "original_paper_date": "6/14/2024 0:00",
    "original_paper_doi": "10.1051/e3sconf/202453801008",
    "original_paper_pubmed_id": "0.0",
    "retraction_nature": "Retraction",
    "reason": "Concerns/Issues about Article;Concerns/Issues about Referencing/Attributions;Investigation by Journal/Publisher;",
    "paywalled": "No",
    "notes": null
}
```

### 8. List Authors

Get top 10 authors with most retractions:

```bash
curl "http://localhost:8000/authors?limit=10"
```

**Response:**
```json
{
    "total": 179411,
    "authors": [
        {
            "name": "Joachim Boldt",
            "retraction_count": 235
        },
        {
            "name": "Yoshitaka Fujii",
            "retraction_count": 219
        },
        {
            "name": "Wei Zhang",
            "retraction_count": 170
        },
        ...
    ]
}
```

### 9. List Journals

Get top 10 journals with most retractions:

```bash
curl "http://localhost:8000/journals?limit=10"
```

**Response:**
```json
{
    "total": 8552,
    "journals": [
        {
            "name": "Journal of Intelligent & Fuzzy Systems",
            "retraction_count": 1565
        },
        {
            "name": "2011 International Conference on E-Business and E-Government (ICEE)",
            "retraction_count": 1280
        },
        {
            "name": "PLoS One",
            "retraction_count": 1270
        },
        ...
    ]
}
```

## Python Examples

### Using requests library

```python
import requests

BASE_URL = "http://localhost:8000"

# Get retractions from 2025
response = requests.get(f"{BASE_URL}/retractions", params={
    "year": 2025,
    "page": 1,
    "page_size": 10
})

data = response.json()
print(f"Found {data['total']} retractions in 2025")

for retraction in data['retractions']:
    print(f"- {retraction['title']}")

# Get a specific retraction
response = requests.get(f"{BASE_URL}/retractions/69157")
retraction = response.json()
print(f"Title: {retraction['title']}")
print(f"Journal: {retraction['journal']}")
print(f"Authors: {retraction['author']}")

# Get top authors
response = requests.get(f"{BASE_URL}/authors", params={"limit": 5})
data = response.json()
print(f"\nTop 5 authors with most retractions:")
for author in data['authors']:
    print(f"{author['name']}: {author['retraction_count']} retractions")
```

## OpenAPI Documentation

Access the interactive API documentation at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Error Responses

### 404 Not Found

When requesting a non-existent retraction:

```bash
curl "http://localhost:8000/retractions/999999999"
```

**Response:**
```json
{
    "detail": "Retraction with ID 999999999 not found"
}
```

### 422 Validation Error

When providing invalid parameters:

```bash
curl "http://localhost:8000/retractions?page=-1"
```

**Response:**
```json
{
    "detail": [
        {
            "loc": ["query", "page"],
            "msg": "ensure this value is greater than or equal to 1",
            "type": "value_error.number.not_ge"
        }
    ]
}
```

## Docker Usage

Build and run with Docker:

```bash
# Build the image
docker build -t retraction-api .

# Run the container
docker run -p 8000:8000 retraction-api

# Access the API
curl http://localhost:8000/
```

## Notes

- All text searches are case-insensitive
- Author names and reasons are semicolon-separated in the data
- Dates are in M/D/YYYY H:MM format
- The database contains 68,489+ records
- Pagination is recommended for large result sets (max 100 items per page)
