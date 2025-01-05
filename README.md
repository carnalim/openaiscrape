# AI Model Explorer

A Python Flask web application that displays information about various AI models available through different providers. The application scrapes model data from OpenRouter.ai and presents it in a user-friendly interface with search functionality and detailed comparisons.

## Features

- Browse a comprehensive list of AI models
- Search models by name or provider
- View detailed model information including:
  - Context length
  - Maximum output tokens
  - Input/Output pricing
  - Provider-specific details
- Compare different providers for each model
- Direct links to provider websites
- Responsive design for mobile and desktop

## Tech Stack

- Python 3.x
- Flask (Web Framework)
- SQLite (Database)
- BeautifulSoup4 (Web Scraping)
- HTML/CSS (Frontend)
- JavaScript (Search functionality)

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ai-model-explorer.git
cd ai-model-explorer
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the scraper to populate the database:
```bash
python scraper.py
```

5. Start the Flask server:
```bash
python app.py
```

6. Open your browser and navigate to:
```
http://localhost:5000
```

## Project Structure

```
ai-model-explorer/
├── app.py              # Flask application
├── scraper.py         # Model data scraper
├── requirements.txt   # Python dependencies
├── static/           # Static files
│   └── css/
│       └── styles.css
├── templates/        # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── models.html
│   └── model_detail.html
└── README.md
```

## Contributing

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.