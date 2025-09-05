# Visual Web Agent

It is a visual web automation agent that analyzes Medium articles using AI-powered summarization and provides personalized reading recommendations based on your interests.

## Features

- ** Visual Web Automation**: Uses Playwright to navigate and capture screenshots of Medium articles
- ** AI-Powered Analysis**: Leverages Google's Gemini 2.5 Flash model for intelligent content summarization
- ** Multi-Stage Processing**: Implements LangGraph workflow for systematic article analysis
- ** Popup Handling**: Automatically detects and closes Medium login popups during scrolling
- ** Personalized Recommendations**: Provides YES/NO recommendations based on your specified interests
- ** Clean Browser Management**: Opens fresh Chromium instance without affecting existing Chrome sessions

## Architecture

The agent follows a multi-stage workflow:

1. **Initialize** - Launch Chromium browser and navigate to article
2. **Screenshot** - Capture visual content of the current viewport
3. **Summarize** - Use Gemini Vision to analyze and summarize screenshot content
4. **Scroll Decision** - Intelligently decide whether to continue scrolling or aggregate results
5. **Aggregate** - Compile all summaries into final analysis and recommendation

## Prerequisites

- Python 3.8+
- Google Gemini API key
- Chrome/Chromium browser

## Installation

1. **Clone the repository**
```
git clone https://github.com/yourusername/medium-article-analyzer.git
cd medium-article-analyzer
```

2. **Install dependencies**
```
pip install -r requirements.txt
```

3. **Install Playwright browsers**
```
playwright install chromium
```

4. **Set up environment variables**
Create .env file
```
echo "GEMINI_API_KEY=your_gemini_api_key_here" > .env
```

## Usage

### Command Line Arguments
```
python medium_analyzer.py --link "ARTICLE_URL" --interests interest1 interest2 --scroll_count 3
```

### Parameters

- `--link`: URL of the Medium article to analyze (required)
- `--interests`: List of your interests for recommendation matching (default: AI Technology)
- `--scroll_count`: Maximum number of scrolls through the article (default: 3)

### Alternative JSON Configuration
```
python medium_analyzer.py --config '{"link": "https://medium.com/@user/article", "interests": ["AI", "Python", "Technology"], "scroll_count": 5}'
```

## Example
```
python medium_analyzer.py
--link "https://medium.com/@itberrios6/introduction-to-point-net-d23f43aa87d2"
--interests "AI" "Machine Learning" "Computer Vision"
--scroll_count 4
```

## Sample Output
```
--- Starting LangGraph Agent ---

--- Step: init ---
-----Initializing new Chromium browser instance-----
-----Chromium browser initialized-----
-----Navigating to the provided URL-----

--- Step: screenshot ---
*****ACTION: taking screenshot of the current browser state
--- Step: summarizer ---

Individual Screenshot Summary:
The screenshot shows a Medium article about Point Net, discussing 3D point cloud processing...

--- Step: aggregate ---

Final Aggregated Summary and Recommendation:
SUMMARY: This article provides an intuitive introduction to Point Net, a neural network architecture designed for processing 3D point clouds. It covers the fundamentals of point cloud data, traditional feature extraction challenges, and how Point Net addresses these through end-to-end learning with transformation networks (T-nets) for rotation invariance.

RECOMMENDATION: YES - This article is highly relevant for someone interested in AI, Machine Learning, and Computer Vision. It bridges traditional computer vision with modern deep learning approaches for 3D data processing, making it valuable for understanding emerging AI applications in spatial computing.
```

### Customization Options

- **Scroll Amount**: Modify the `viewport_height * 0.8` multiplier in `scroll_down()` tool
- **Screenshot Quality**: Adjust Playwright screenshot options in `take_ss()` tool  
- **Popup Selectors**: Update `close_selectors` in `close_login_popup_if_present()` for different sites
- **Model Selection**: Change the Gemini model in the `llm` initialization

### Performance Tips

- **Reduce scroll_count** for faster analysis of shorter articles
- **Increase scroll_count** for comprehensive analysis of longer content
- **Adjust viewport height multiplier** for different scroll distances