
#!/usr/bin/env python3
"""
JSON to Tabular Converter - Standalone Version
Run this file to start the Flask server in VS Code
"""

import json
import pandas as pd
from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import os
from werkzeug.utils import secure_filename
import tempfile
from datetime import datetime
import uuid
import gc
import json
import csv
try:
    import ijson
except Exception:
    ijson = None

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 100MB max file size

ALLOWED_EXTENSIONS = {'json'}
OUTPUT_FORMATS = ['csv', 'excel']

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def flatten_json(data, parent_key='', sep='_'):
    """Flatten nested JSON structure"""
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Handle arrays
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        items.extend(flatten_json(item, f"{new_key}{sep}{i}", sep=sep).items())
                    else:
                        items.append((f"{new_key}{sep}{i}", item))
            else:
                items.append((new_key, v))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                items.extend(flatten_json(item, f"{parent_key}{sep}{i}", sep=sep).items())
            else:
                items.append((f"{parent_key}{sep}{i}", item))
    else:
        items.append((parent_key, data))
    
    return dict(items)


def stream_convert_file(file_storage, combined_file_path, sample_size=500, max_preview=20):
    """Stream-parse incoming JSON/JSONL and write to CSV incrementally.
    Uses ijson if available (for large JSON arrays). For JSONL, falls back to line-by-line parsing.
    Returns (total_rows, header, preview_rows)
    """
    stream = file_storage.stream
    def line_iterator(s):
        for raw in s:
            if isinstance(raw, bytes):
                line = raw.decode('utf-8')
            else:
                line = raw
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)

    if ijson:
        try:
            iterator = ijson.items(stream, 'item')
        except Exception:
            try:
                stream.seek(0)
            except Exception:
                pass
            iterator = line_iterator(stream)
    else:
        try:
            stream.seek(0)
        except Exception:
            pass
        iterator = line_iterator(stream)

    sampled = []
    total_rows = 0
    preview_rows = []

    for _ in range(sample_size):
        try:
            obj = next(iterator)
        except StopIteration:
            break
        sampled.append(obj)

    header_keys = set()
    for obj in sampled:
        flat = flatten_json(obj)
        header_keys.update(flat.keys())

    EXTRA_COL = '_extra'
    header = sorted(list(header_keys))
    if EXTRA_COL not in header:
        header.append(EXTRA_COL)

    with open(combined_file_path, 'w', encoding='utf-8', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        writer.writeheader()

        def write_flat(flat_obj):
            row = {k: flat_obj.get(k, '') for k in header if k != EXTRA_COL}
            extra = {k: v for k, v in flat_obj.items() if k not in row}
            if extra:
                row[EXTRA_COL] = json.dumps(extra, ensure_ascii=False)
            else:
                row[EXTRA_COL] = ''
            writer.writerow(row)

        for obj in sampled:
            flat = flatten_json(obj)
            write_flat(flat)
            total_rows += 1
            if len(preview_rows) < max_preview:
                preview_rows.append(flat)

        for obj in iterator:
            try:
                flat = flatten_json(obj)
            except Exception:
                continue
            write_flat(flat)
            total_rows += 1
            if len(preview_rows) < max_preview:
                preview_rows.append(flat)

    return total_rows, header, preview_rows

def json_to_dataframe(json_data):
    """Convert JSON data to pandas DataFrame"""
    if isinstance(json_data, list):
        # If it's a list of objects, try to normalize
        if all(isinstance(item, dict) for item in json_data):
            # Flatten each object and create DataFrame
            flattened_data = [flatten_json(item) for item in json_data]
            df = pd.DataFrame(flattened_data)
        else:
            # If it's a simple list, convert to single column DataFrame
            df = pd.DataFrame(json_data, columns=['value'])
    elif isinstance(json_data, dict):
        # Flatten the dictionary and create DataFrame with one row
        flattened = flatten_json(json_data)
        df = pd.DataFrame([flattened])
    else:
        # Single value
        df = pd.DataFrame([json_data], columns=['value'])
    
    return df

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['file']
    output_format = request.form.get('output_format', 'csv')
    
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    if file and allowed_file(file.filename):
        try:
            # Read and parse JSON
            json_content = file.read().decode('utf-8')
            
            # Try to parse as standard JSON first
            try:
                json_data = json.loads(json_content)
            except json.JSONDecodeError:
                # If that fails, try parsing as JSON Lines (JSONL)
                lines = json_content.strip().split('\n')
                json_data = []
                for line_num, line in enumerate(lines, 1):
                    if line.strip():  # Skip empty lines
                        try:
                            json_data.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            raise json.JSONDecodeError(f"Invalid JSON on line {line_num}: {str(e)}", line, e.pos)
            
            # Convert to DataFrame
            df = json_to_dataframe(json_data)
            
            # Store data in session for preview
            session_id = str(uuid.uuid4())
            
            # Create temporary file to store converted data
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                df.to_csv(tmp_file.name, index=False)
                temp_file_path = tmp_file.name
            
            # Store session data
            session_data = {
                'df_path': temp_file_path,
                'original_filename': secure_filename(file.filename),
                'output_format': output_format,
                'df_shape': df.shape,
                'df_columns': list(df.columns)
            }
            
            # You could use a proper session store in production
            # For now, we'll pass the data to the preview page
            preview_data = {
                'df_html': df.head(20).to_html(classes='table table-striped', table_id='preview-table', escape=False),
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'columns': list(df.columns),
                'original_filename': secure_filename(file.filename),
                'output_format': output_format,
                'session_id': session_id
            }
            
            # Store in a simple in-memory cache (use Redis in production)
            if not hasattr(app, 'preview_cache'):
                app.preview_cache = {}
            app.preview_cache[session_id] = session_data
            
            return render_template('preview.html', **preview_data)
                
        except json.JSONDecodeError:
            flash('Invalid JSON file. Please check your file format.')
        except Exception as e:
            flash(f'Error processing file: {str(e)}')
    else:
        flash('Invalid file format. Please upload a JSON file.')
    
    return redirect(url_for('index'))

@app.route('/download/<session_id>')
def download_file(session_id):
    if not hasattr(app, 'preview_cache') or session_id not in app.preview_cache:
        flash('Session expired or invalid')
        return redirect(url_for('index'))
    
    session_data = app.preview_cache[session_id]
    
    try:
        # Read the stored DataFrame
        df = pd.read_csv(session_data['df_path'])
        
        # Generate output filename
        base_name = os.path.splitext(session_data['original_filename'])[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_format = session_data['output_format']
        
        # Create temporary file for download
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            if output_format == 'csv':
                output_filename = f"{base_name}_converted_{timestamp}.csv"
                df.to_csv(tmp_file.name, index=False)
                mimetype = 'text/csv'
            else:  # excel
                output_filename = f"{base_name}_converted_{timestamp}.xlsx"
                df.to_excel(tmp_file.name, index=False, engine='openpyxl')
                mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            
            # Clean up stored file
            try:
                os.unlink(session_data['df_path'])
                del app.preview_cache[session_id]
            except:
                pass
            
            return send_file(
                tmp_file.name,
                as_attachment=True,
                download_name=output_filename,
                mimetype=mimetype
            )
    except Exception as e:
        flash(f'Error generating download: {str(e)}')
        return redirect(url_for('index'))

@app.route('/api/convert', methods=['POST'])
def api_convert():
    """API endpoint for programmatic conversion"""
    try:
        if 'file' not in request.files:
            return {'error': 'No file provided'}, 400
        
        file = request.files['file']
        output_format = request.form.get('output_format', 'csv')
        
        if not allowed_file(file.filename):
            return {'error': 'Invalid file format'}, 400
        
        # Read and parse JSON
        json_content = file.read().decode('utf-8')
        
        # Try to parse as standard JSON first
        try:
            json_data = json.loads(json_content)
        except json.JSONDecodeError:
            # If that fails, try parsing as JSON Lines (JSONL)
            lines = json_content.strip().split('\n')
            json_data = []
            for line_num, line in enumerate(lines, 1):
                if line.strip():  # Skip empty lines
                    try:
                        json_data.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        raise json.JSONDecodeError(f"Invalid JSON on line {line_num}: {str(e)}", line, e.pos)
        
        # Convert to DataFrame
        df = json_to_dataframe(json_data)
        
        # Return basic info about conversion
        return {
            'status': 'success',
            'rows': len(df),
            'columns': len(df.columns),
            'column_names': list(df.columns)
        }
        
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    print("Starting JSON to Tabular Converter...")
    print("Open your browser and go to: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    app.run(host='0.0.0.0', port=5000, debug=True)
