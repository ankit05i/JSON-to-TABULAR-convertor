import json
import pandas as pd
from flask import Flask, render_template, request, send_file, flash, redirect, url_for, Response
import os
from werkzeug.utils import secure_filename
import tempfile
from datetime import datetime
import uuid
import gc
from io import StringIO
import csv

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # Increased to 500MB

ALLOWED_EXTENSIONS = {'json'}
OUTPUT_FORMATS = ['csv', 'excel']
CHUNK_SIZE = 1000  # Process in chunks of 1000 records

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def flatten_json(data, parent_key='', sep='_'):
    """Flatten nested JSON structure - optimized version"""
    items = []
    if isinstance(data, dict):
        for k, v in data.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_json(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                # Handle arrays more efficiently
                if len(v) > 0:
                    # For large arrays, only sample first few items to determine structure
                    sample_size = min(10, len(v))
                    for i in range(sample_size):
                        item = v[i]
                        if isinstance(item, dict):
                            items.extend(flatten_json(item, f"{new_key}{sep}{i}", sep=sep).items())
                        else:
                            items.append((f"{new_key}{sep}{i}", item))
                    # For remaining items in large arrays, use a more compact representation
                    if len(v) > sample_size:
                        items.append((f"{new_key}_count", len(v)))
            else:
                items.append((new_key, v))
    elif isinstance(data, list):
        # Handle large lists more efficiently
        sample_size = min(10, len(data))
        for i in range(sample_size):
            item = data[i]
            if isinstance(item, dict):
                items.extend(flatten_json(item, f"{parent_key}{sep}{i}", sep=sep).items())
            else:
                items.append((f"{parent_key}{sep}{i}", item))
        if len(data) > sample_size:
            items.append((f"{parent_key}_total_count", len(data)))
    else:
        items.append((parent_key, data))
    
    return dict(items)

def process_json_chunks(json_data, chunk_size=CHUNK_SIZE):
    """Process JSON data in chunks to handle large datasets"""
    if isinstance(json_data, list):
        # Process list in chunks
        for i in range(0, len(json_data), chunk_size):
            chunk = json_data[i:i + chunk_size]
            if all(isinstance(item, dict) for item in chunk):
                # Flatten each object in the chunk
                flattened_chunk = [flatten_json(item) for item in chunk]
                yield pd.DataFrame(flattened_chunk)
            else:
                # Simple list chunk
                yield pd.DataFrame(chunk, columns=['value'])
            
            # Force garbage collection after each chunk
            gc.collect()
    else:
        # Single object or simple value
        if isinstance(json_data, dict):
            flattened = flatten_json(json_data)
            yield pd.DataFrame([flattened])
        else:
            yield pd.DataFrame([json_data], columns=['value'])

def parse_large_json_file(file_content):
    """Parse JSON with fallback to streaming for large files"""
    try:
        # Try standard JSON parsing first
        return json.loads(file_content)
    except json.JSONDecodeError:
        # Try JSON Lines format
        lines = file_content.strip().split('\n')
        json_data = []
        for line_num, line in enumerate(lines, 1):
            if line.strip():
                try:
                    json_data.append(json.loads(line))
                    # If we're processing too many lines, break early for memory
                    if line_num > 100000:  # Limit for very large JSONL files
                        break
                except json.JSONDecodeError as e:
                    if line_num <= 100:  # Only show errors for first 100 lines
                        raise json.JSONDecodeError(f"Invalid JSON on line {line_num}: {str(e)}", line, e.pos)
        return json_data

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
            # Read file content
            json_content = file.read().decode('utf-8')
            
            # Check file size and warn user
            file_size = len(json_content)
            if file_size > 50 * 1024 * 1024:  # 50MB
                flash('Large file detected. Processing may take a moment...')
            
            # Parse JSON with optimizations for large files
            json_data = parse_large_json_file(json_content)
            
            # Process in chunks and combine results
            all_columns = set()
            chunk_files = []
            total_rows = 0
            
            # First pass: collect all columns and save chunks
            for chunk_df in process_json_chunks(json_data):
                if not chunk_df.empty:
                    all_columns.update(chunk_df.columns)
                    total_rows += len(chunk_df)
                    
                    # Save chunk to temporary file
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', encoding='utf-8', newline='') as tmp_file:
                        chunk_df.to_csv(tmp_file, index=False)
                        chunk_files.append(tmp_file.name)
            
            # Create final combined file with consistent columns
            combined_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', encoding='utf-8', newline='')
            combined_file_path = combined_file.name
            all_columns = sorted(list(all_columns))
            
            # Write header
            writer = csv.writer(combined_file)
            writer.writerow(all_columns)
            combined_file.close()  # Close before appending
            
            # Combine all chunks with consistent columns
            for chunk_file in chunk_files:
                try:
                    if os.path.exists(chunk_file):
                        chunk_df = pd.read_csv(chunk_file)
                        # Reindex to ensure all columns are present
                        chunk_df = chunk_df.reindex(columns=all_columns, fill_value='')
                        # Write chunk data to combined file
                        with open(combined_file_path, 'a', encoding='utf-8', newline='') as f:
                            chunk_df.to_csv(f, header=False, index=False)
                        
                        # Clean up chunk file after successful read
                        os.unlink(chunk_file)
                    gc.collect()
                except Exception as chunk_error:
                    # Log the error but continue processing
                    print(f"Error processing chunk file {chunk_file}: {chunk_error}")
                    # Try to clean up the problematic chunk file
                    try:
                        if os.path.exists(chunk_file):
                            os.unlink(chunk_file)
                    except:
                        pass
            
            # Create preview from the combined file
            try:
                preview_df = pd.read_csv(combined_file_path, nrows=20)
                preview_rows = min(20, len(preview_df))
            except Exception as preview_error:
                # Fallback: create empty preview
                preview_df = pd.DataFrame(columns=all_columns)
                preview_rows = 0
            
            # Store session data
            session_id = str(uuid.uuid4())
            session_data = {
                'df_path': combined_file_path,
                'original_filename': secure_filename(file.filename),
                'output_format': output_format,
                'df_shape': (total_rows, len(all_columns)),
                'df_columns': all_columns
            }
            
            preview_data = {
                'df_html': preview_df.head(preview_rows).to_html(classes='table table-striped', table_id='preview-table', escape=False),
                'total_rows': total_rows,
                'total_columns': len(all_columns),
                'columns': all_columns,
                'original_filename': secure_filename(file.filename),
                'output_format': output_format,
                'session_id': session_id,
                'is_large_file': total_rows > 10000
            }
            
            # Store in cache
            if not hasattr(app, 'preview_cache'):
                app.preview_cache = {}
            app.preview_cache[session_id] = session_data
            
            return render_template('preview.html', **preview_data)
                
        except json.JSONDecodeError as e:
            flash(f'Invalid JSON file: {str(e)}')
        except MemoryError:
            flash('File too large to process. Please try a smaller file or contact support.')
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
        # Generate output filename
        base_name = os.path.splitext(session_data['original_filename'])[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_format = session_data['output_format']
        
        if output_format == 'csv':
            # For CSV, stream the file directly
            output_filename = f"{base_name}_converted_{timestamp}.csv"
            
            def generate_csv():
                with open(session_data['df_path'], 'r', encoding='utf-8') as f:
                    for line in f:
                        yield line.encode('utf-8')
            
            # Clean up
            try:
                if os.path.exists(session_data['df_path']):
                    os.unlink(session_data['df_path'])
                if session_id in app.preview_cache:
                    del app.preview_cache[session_id]
            except Exception as cleanup_error:
                print(f"Cleanup error: {cleanup_error}")
                pass
            
            return Response(
                generate_csv(),
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename={output_filename}'}
            )
        else:
            # For Excel, we need to load and convert (less memory efficient)
            output_filename = f"{base_name}_converted_{timestamp}.xlsx"
            
            # Read in chunks and write to Excel
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp_file:
                # For very large files, we'll need to read in chunks
                chunk_reader = pd.read_csv(session_data['df_path'], chunksize=5000)
                
                with pd.ExcelWriter(tmp_file.name, engine='openpyxl') as writer:
                    start_row = 0
                    for chunk in chunk_reader:
                        chunk.to_excel(writer, sheet_name='Sheet1', startrow=start_row, 
                                     header=(start_row == 0), index=False)
                        start_row += len(chunk)
                        gc.collect()
                
                # Clean up
                try:
                    if os.path.exists(session_data['df_path']):
                        os.unlink(session_data['df_path'])
                    if session_id in app.preview_cache:
                        del app.preview_cache[session_id]
                except Exception as cleanup_error:
                    print(f"Cleanup error: {cleanup_error}")
                    pass
                
                return send_file(
                    tmp_file.name,
                    as_attachment=True,
                    download_name=output_filename,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
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
        json_data = parse_large_json_file(json_content)
        
        # Quick analysis without full processing
        total_rows = 0
        columns = set()
        
        for chunk_df in process_json_chunks(json_data):
            if not chunk_df.empty:
                columns.update(chunk_df.columns)
                total_rows += len(chunk_df)
                # Only process first few chunks for API response
                if total_rows > 10000:
                    break
        
        return {
            'status': 'success',
            'rows': total_rows,
            'columns': len(columns),
            'column_names': sorted(list(columns)),
            'estimated': total_rows > 10000
        }
        
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
