# OpenRouter.ai Model Scraper

A Python web application that scrapes and displays AI model information from OpenRouter.ai.

## Features

- Scrapes model information from OpenRouter.ai
- Displays models in a clean, responsive web interface
- Shows detailed provider information for each model
- Stores data in SQLite database
- Lists context lengths, pricing, and other model stats

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Visit http://127.0.0.1:5001 in your browser

## Project Structure

- `app.py` - Flask web application
- `scraper.py` - Model data scraper
- `templates/` - HTML templates
  - `base.html` - Base template with navigation
  - `index.html` - Home page
  - `models.html` - Models listing page
  - `model_detail.html` - Individual model details
  - `404.html` - Not found error page
  - `500.html` - Server error page
- `requirements.txt` - Python dependencies

## Technologies Used

- Python 3
- Flask
- BeautifulSoup4
- SQLite
- HTML/CSS