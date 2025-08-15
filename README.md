# 🔄 JSON to Table Converter

Convert your JSON files to Excel or CSV format instantly! Perfect for data analysis and spreadsheet work.

## ✨ What This Does

This tool takes messy JSON data and turns it into clean, organized tables that you can open in Excel, Google Sheets, or any spreadsheet program.

### Before (JSON):
```json
{"name": "John", "age": 30, "address": {"city": "NYC", "zip": "10001"}}
```

### After (Table):
| name | age | address_city | address_zip |
|------|-----|--------------|-------------|
| John | 30  | NYC          | 10001       |

## 🚀 How to Use

### Option 1: Run in Replit (Easiest)
1. Click the **Run** button at the top
2. Open the preview link when it appears
3. Upload your JSON file
4. Download your converted table!

### Option 2: Download and Run Locally
1. Download all files to your computer
2. **Windows**: Double-click `setup_and_run.bat`
3. **Mac/Linux**: Run `./setup_and_run.sh` in terminal
4. Open `http://localhost:5000` in your browser

## 📁 What JSON Files Work?

✅ **Simple objects**
```json
{"name": "John", "age": 30}
```

✅ **Lists of data**
```json
[
  {"name": "John", "age": 30},
  {"name": "Jane", "age": 25}
]
```

✅ **Complex nested data**
```json
{
  "user": {
    "personal": {"name": "John", "age": 30},
    "contact": {"email": "john@email.com"}
  }
}
```

✅ **JSON Lines files** (one JSON object per line)
```json
{"name": "John", "age": 30}
{"name": "Jane", "age": 25}
```

## 🎯 Features

- 📤 **Drag & Drop**: Just drag your JSON file onto the page
- 👀 **Preview First**: See your data before downloading
- 📊 **Two Formats**: Export as CSV or Excel (.xlsx)
- 🔧 **Smart Flattening**: Automatically handles nested data
- 📏 **Big Files**: Supports files up to 100MB
- 🌐 **No Internet Required**: Works completely offline

## 💡 Common Use Cases

- **API Data**: Convert API responses to spreadsheets
- **Log Files**: Analyze JSON log data in Excel
- **Database Exports**: Turn JSON exports into tables
- **Data Science**: Prepare JSON data for analysis
- **Reports**: Create readable reports from complex data

## 🛠️ Technical Details

- Built with Python Flask
- Uses pandas for data processing
- Supports nested JSON structures
- Automatically flattens complex data
- Web-based interface for easy use

## 📋 File Structure

```
json-converter/
├── run_server.py        # Main application
├── templates/           # Web pages
├── requirements.txt     # Dependencies
├── setup_and_run.bat   # Windows setup
├── setup_and_run.sh    # Mac/Linux setup
└── README.md           # This file
```

## ❓ Need Help?

**Q: My JSON file won't upload**
A: Make sure it's a .json file and under 100MB

**Q: The output looks weird**
A: Complex nested data gets flattened with underscores (e.g., `user_address_city`)

**Q: Can I use this for large datasets?**
A: Yes! Supports files up to 100MB

**Q: Is my data safe?**
A: Yes! Everything processes locally, no data is sent to external servers

## 🔧 For Developers

### API Usage
```bash
curl -X POST \
  -F "file=@data.json" \
  -F "output_format=csv" \
  http://localhost:5000/api/convert
```

### Requirements
- Python 3.7+
- Flask, pandas, openpyxl

---

**Ready to convert your JSON data? Hit the Run button and get started! 🚀**

## 🚢 Deployment notes (large uploads)

If you plan to accept very large uploads (hundreds of MB to multiple GB), adjust your web server and WSGI settings:

- Flask: set `app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024` for 5GB uploads.
- nginx: in your server block set `client_max_body_size 5G;` and increase timeouts:
  - `client_body_timeout 600s;`
  - `proxy_read_timeout 600s;`
  - `proxy_connect_timeout 600s;`
- Gunicorn: increase the timeout and use an appropriate worker class. Example:
  - `gunicorn -w 4 -k gthread --threads 4 --timeout 600 run_server:app`

Notes:
- Use streaming parsing (the project includes a streaming path using `ijson`/line-by-line JSONL) so the server does not load the whole upload into memory.
- For very large uploads consider direct-to-cloud uploads (S3 multipart) and process from storage instead of routing through the Flask server.

## ✅ Quick test for streaming path

1. Install dependencies:
```
pip install -r requirements.txt
```
2. Start the server:
```
python run_server.py
```
3. Upload a JSONL file (one JSON object per line) via the web UI and verify the preview and download work; this exercises the streaming conversion path.
