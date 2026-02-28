#!/usr/bin/env python3

import json
import sys
import argparse
import os
from datetime import datetime, timedelta
import time
import signal
import termios
import tty
import glob
from pathlib import Path

def convert_timestamp(timestamp_str):
    """Convert ISO 8601 timestamp to HH:MM:SS format with GMT+8 adjustment"""
    try:
        # Parse the timestamp string (assuming ISO 8601 format)
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Add 8 hours for GMT+8
        dt_gmt8 = dt + timedelta(hours=8)
        return dt_gmt8.strftime('%H:%M:%S')
    except Exception:
        # If parsing fails, return original timestamp
        return timestamp_str

def get_color_code(field_name):
    """Generate a consistent color code based on field name"""
    if not field_name:
        return ''

    # Hash the field name to get a consistent color assignment
    hash_val = 0
    for char in field_name:
        hash_val = (hash_val * 31 + ord(char)) & 0x7FFFFFFF

    # Use modulo to get a color from predefined list
    colors = [
        '\033[31m',  # Red
        '\033[32m',  # Green
        '\033[33m',  # Yellow
        '\033[34m',  # Blue
        '\033[35m',  # Magenta
        '\033[36m',  # Cyan
        '\033[91m',  # Bright Red
        '\033[92m',  # Bright Green
        '\033[93m',  # Bright Yellow
        '\033[94m',  # Bright Blue
        '\033[95m',  # Bright Magenta
        '\033[96m',  # Bright Cyan
        '\033[97m',  # White
    ]
    return colors[hash_val % len(colors)]

def print_nested_fields(obj, indent_level=1):
    """Recursively print nested fields with proper indentation"""
    indent = "  " * indent_level

    if isinstance(obj, dict):
        for key, value in obj.items():
            color = get_color_code(key)
            if isinstance(value, dict):
                print(f"{indent}{color}{key}:\033[0m")  # Print the key without {...}
                print_nested_fields(value, indent_level + 1)  # Recursively print nested content
            elif isinstance(value, list):
                print(f"{indent}{color}{key}:\033[0m")  # Print the key without [...]
                # Print list items if they're simple values or objects
                for i, item in enumerate(value):
                    item_indent = "  " * (indent_level + 1)
                    if isinstance(item, dict):
                        print(f"{item_indent}[{i}]:")
                        print_nested_fields(item, indent_level + 2)
                    else:
                        print(f"{item_indent}[{i}]: {item}")
            elif isinstance(value, str):
                # Handle escaped strings in content
                processed_value = value.replace('\\n', ' ').replace('\\t', '    ').replace('\\"', '"')
                print(f"{indent}{color}{key}:\033[0m {processed_value}")
            else:
                print(f"{indent}{color}{key}:\033[0m {value}")
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            item_indent = "  " * indent_level
            if isinstance(item, dict):
                print(f"{item_indent}[{i}]:")
                print_nested_fields(item, indent_level + 1)
            else:
                print(f"{item_indent}[{i}]: {item}")

def format_log_entry(json_obj):
    """Format and print a log entry"""
    # Print a blank line before each log entry
    print()

    timestamp = json_obj.get('timestamp', json_obj.get('time', None))
    entry_type = json_obj.get('type', None)

    # Format timestamp with GMT+8 conversion
    formatted_time = ''
    if timestamp:
        formatted_time = convert_timestamp(timestamp)

    # Print the header with timestamp and type
    if formatted_time and entry_type:
        print(f"\033[36m[{formatted_time}]\033[0m {get_color_code(entry_type)}[{entry_type}]\033[0m")
    elif formatted_time:
        print(f"\033[36m[{formatted_time}]\033[0m \033[33m[unknown-type]\033[0m")
    elif entry_type:
        print(f"\033[33m[No timestamp]\033[0m {get_color_code(entry_type)}[{entry_type}]\033[0m")
    else:
        print("\033[33m[No timestamp or type]\033[0m")

    # Print all fields, handling special cases for log formats
    for key, value in json_obj.items():
        if key in ['timestamp', 'type', 'time']:  # Also exclude 'time' if it's duplicate
            continue

        if isinstance(value, dict):
            # For nested objects, print the field name and then expand its contents fully
            color = get_color_code(key)
            print(f"  {color}{key}:\033[0m")
            print_nested_fields(value, 2)  # Just print the nested content, no "{...}"
        elif isinstance(value, list):
            # For arrays, print the field name and then expand its contents
            color = get_color_code(key)
            print(f"  {color}{key}:\033[0m")
            for i, item in enumerate(value):
                item_indent = "  " * 2
                if isinstance(item, dict):
                    print(f"{item_indent}[{i}]:")
                    print_nested_fields(item, 3)
                else:
                    print(f"{item_indent}[{i}]: {item}")
        elif isinstance(value, str):
            # Determine appropriate color for the field
            color = get_color_code(key)

            # Special handling for the "0" field (first argument in logging libraries)
            if key == "0":
                # This is often the main log message
                processed_value = value.replace('\\n', ' ').replace('\\t', '    ').replace('\\"', '"')
                print(f"  {color}message:\033[0m {processed_value}")
            else:
                # Handle escaped strings in content
                processed_value = value.replace('\\n', ' ').replace('\\t', '    ').replace('\\"', '"')
                print(f"  {color}{key}:\033[0m {processed_value}")
        else:
            # For primitive types (int, float, boolean, etc.)
            color = get_color_code(key)
            print(f"  {color}{key}:\033[0m {value}")

def find_latest_file(directory_path=None):
    """Find the latest modified file in the given directory, or auto-detect Qwen project dir"""
    # Auto-detect Qwen project directory if not provided
    if directory_path is None:
        directory_path = find_qwen_project_dir()
        if directory_path is None:
            raise FileNotFoundError("Cannot find Qwen project directory. Please specify a path.")

    directory = Path(directory_path)

    # Find all files in the directory (including subdirectories)
    files = [f for f in directory.rglob('*') if f.is_file()]

    if not files:
        raise FileNotFoundError(f"No files found in directory: {directory_path}")

    # Sort files by modification time, newest first
    latest_file = max(files, key=lambda f: f.stat().st_mtime)

    print(f"Using latest file: {latest_file}")
    return str(latest_file)


def find_qwen_project_dir():
    """Find the Qwen project directory automatically."""
    home = Path.home()
    projects_dir = home / ".qwen" / "projects"

    if not projects_dir.is_dir():
        return None

    # Find subdirectories that contain .jsonl files
    subdirs = [d for d in projects_dir.iterdir() if d.is_dir()]
    subdirs_with_jsonl = []

    for d in subdirs:
        # Check 'chats' subdirectory within this dir (common Qwen structure)
        chats_subdir = d / "chats"
        if chats_subdir.is_dir():
            jsonl_files = list(chats_subdir.glob("*.jsonl"))
            if jsonl_files:
                subdirs_with_jsonl.append(chats_subdir)
                continue
        # Check direct children for .jsonl files
        direct_jsonl = list(d.glob("*.jsonl"))
        if direct_jsonl:
            subdirs_with_jsonl.append(d)

    if not subdirs_with_jsonl:
        return None

    # Prioritize workspace-related directories with newer data
    # Return the one with the most recent .jsonl file
    latest_file_time = 0
    best_dir = None
    for subdir in subdirs_with_jsonl:
        jsonl_files = list(subdir.rglob("*.jsonl"))
        if jsonl_files:
            newest_mtime = max(f.stat().st_mtime for f in jsonl_files)
            if newest_mtime > latest_file_time:
                latest_file_time = newest_mtime
                best_dir = subdir

    return best_dir

def find_next_timestamp_index(lines, start_index):
    """Find the next line that contains a log entry with a timestamp"""
    for i in range(start_index, len(lines)):
        try:
            json_obj = json.loads(lines[i].strip())
            # Look for timestamp field (or time for different log formats)
            if 'timestamp' in json_obj or 'time' in json_obj or 'type' in json_obj:
                return i
        except json.JSONDecodeError:
            # Skip non-JSON lines
            continue
    return len(lines)  # Return end of file if not found

def get_log_summary(lines):
    """Extract log summary information"""
    total_events = 0
    timestamps = []

    for line in lines:
        try:
            json_obj = json.loads(line.strip())
            # Look for timestamp field (or time for different log formats)
            timestamp = json_obj.get('timestamp') or json_obj.get('time')
            if timestamp:
                try:
                    # Validate that it's a proper timestamp
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamps.append(dt)
                except ValueError:
                    # Skip invalid timestamps
                    pass
            total_events += 1
        except json.JSONDecodeError:
            # Count non-JSON lines as well
            total_events += 1

    start_time = None
    end_time = None

    if timestamps:
        start_time = min(timestamps)
        end_time = max(timestamps)

        # Convert to YYYY-MM-DD HH:MM:SS format with GMT+8
        start_time_gmt8 = start_time + timedelta(hours=8)
        end_time_gmt8 = end_time + timedelta(hours=8)

        start_str = start_time_gmt8.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time_gmt8.strftime('%Y-%m-%d %H:%M:%S')
    else:
        start_str = "N/A"
        end_str = "N/A"

    # Calculate total pages (lines_per_page = 20)
    lines_per_page = 20
    total_pages = (len(lines) + lines_per_page - 1) // lines_per_page  # Ceiling division

    return {
        'total_events': total_events,
        'start_time': start_str,
        'end_time': end_str,
        'total_pages': total_pages
    }

def paginate_output(lines, lines_per_page=20):
    """Display content with pagination - jump to next timestamp on Enter"""
    # Get and display log summary first
    summary = get_log_summary(lines)
    print("=" * 50)
    print(f"日志汇总:")
    print(f"  事件数: {summary['total_events']}")
    print(f"  开始时间: {summary['start_time']}")
    print(f"  结束时间: {summary['end_time']}")
    print(f"  总页数: {summary['total_pages']}")
    print("=" * 50)
    print()

    # Wait for user input before continuing
    print("按 'c' 继续查看日志内容，按 'q' 退出: ", end='', flush=True)

    # Read a character from stdin
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    print()  # New line after user input

    if ch.lower() == 'q':
        print("退出...")
        return
    elif ch.lower() != 'c':
        # If user pressed any other key, still continue but inform them
        print("继续...")

    print("格式化输出日志内容...")
    print("按空格键翻页，按回车键跳转到下一个时间戳，按 'q' 退出")
    print("===========================================")

    total_lines = len(lines)
    current_line = 0

    while current_line < total_lines:
        # Display a page worth of lines
        lines_displayed = 0

        while current_line < total_lines and lines_displayed < lines_per_page:
            try:
                json_obj = json.loads(lines[current_line].strip())
                format_log_entry(json_obj)
            except json.JSONDecodeError:
                # If it's not JSON, print as raw line
                print(f"📄 原始行: {lines[current_line]}")

            current_line += 1
            lines_displayed += 1

        if current_line >= total_lines:
            print("文件结束.")
            break

        # Wait for user input
        print("--More--(按空格键翻页，按回车键跳转到下一个时间戳，按 'q' 退出): ", end='', flush=True)

        # Read a character from stdin
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        print()  # New line after user input

        if ch.lower() == 'q':
            print("退出...")
            break
        elif ch == ' ':
            # Show next page (continue the normal flow)
            continue
        elif ch == '\n' or ch == '\r':  # Enter key - jump to next timestamp
            next_timestamp_idx = find_next_timestamp_index(lines, current_line)
            if next_timestamp_idx < len(lines):
                # Display the log entry at the next timestamp position
                try:
                    json_obj = json.loads(lines[next_timestamp_idx].strip())
                    format_log_entry(json_obj)
                except json.JSONDecodeError:
                    print(f"📄 原始行: {lines[next_timestamp_idx]}")

                # Update the current line position
                current_line = next_timestamp_idx + 1
            else:
                print("文件结束.")
                break
        else:
            # Any other key - continue normally
            continue

def get_currently_tracking_file(directory_path=None):
    """Get the currently tracking file path and its inode for change detection"""
    if directory_path is None:
        directory_path = find_qwen_project_dir()
    if directory_path is None:
        return None, None

    directory = Path(directory_path)

    # Find all .jsonl files in the directory
    files = list(directory.rglob("*.jsonl"))
    if not files:
        return None, None

    # Get the most recently modified file
    latest_file = max(files, key=lambda f: f.stat().st_mtime)
    try:
        return str(latest_file), latest_file.stat().st_ino
    except (OSError, FileNotFoundError):
        return None, None


def tail_follow(file_path=None, directory_path=None):
    """Follow a file and output new content as it's appended.
    Automatically detects if Qwen creates a new log file and switches to it.
    """
    print("Following log with beautiful formatting...")
    print("Press Ctrl+C to stop")
    print("===========================================")

    # Auto-detect directory if not provided
    if directory_path is None and file_path is None:
        directory_path = find_qwen_project_dir()
        if directory_path is None:
            print("Error: Cannot find Qwen project directory.")
            sys.exit(1)
    elif file_path is None:
        # Only directory provided, find latest file
        file_path, _ = get_currently_tracking_file(directory_path)
        if file_path is None:
            print(f"Error: No .jsonl files found in {directory_path}")
            sys.exit(1)

    # If file_path is provided but directory_path is not, try to find the directory
    if file_path is not None and directory_path is None:
        p = Path(file_path)
        if p.is_file():
            directory_path = str(p.parent)
        else:
            print(f"Error: Cannot determine directory for {file_path}")
            sys.exit(1)

    # Get the initial file's inode for change detection
    try:
        current_inode = Path(file_path).stat().st_ino
    except (OSError, FileNotFoundError):
        print(f"Error: Cannot access {file_path}")
        sys.exit(1)

    print(f"Monitoring: {file_path}")
    print(f"Monitoring directory: {directory_path}")

    # Open file and go to the end initially
    try:
        f = open(file_path, 'r')
        f.seek(0, os.SEEK_END)
    except IOError as e:
        print(f"Error opening file: {e}")
        sys.exit(1)

    try:
        while True:
            line = f.readline()
            if line:
                try:
                    json_obj = json.loads(line.strip())
                    format_log_entry(json_obj)
                except json.JSONDecodeError:
                    # If it's not JSON, print as raw line
                    print(f"📄 Raw Line: {line.strip()}")
            else:
                # No new line, check if file was rotated/renamed
                time.sleep(0.1)

                # Try to get current file info
                try:
                    current_path = Path(file_path)
                    new_inode = current_path.stat().st_ino

                    # If inode changed, file was replaced
                    if new_inode != current_inode:
                        print(f"\nDetected new log file, switching to: {file_path}")
                        f.close()
                        f = open(file_path, 'r')
                        f.seek(0, os.SEEK_END)
                        current_inode = new_inode
                except (OSError, FileNotFoundError):
                    # File was deleted or moved, look for new log file
                    print(f"\nLog file rotated, finding new log file...")
                    f.close()

                    # Look for the latest .jsonl file in the directory
                    new_file_path, new_inode = get_currently_tracking_file(directory_path)
                    if new_file_path and new_file_path != file_path:
                        print(f"Switching to new log file: {new_file_path}")
                        file_path = new_file_path
                        f = open(file_path, 'r')
                        f.seek(0, os.SEEK_END)
                        current_inode = new_inode
                    elif new_file_path:
                        # Same file, just wait
                        time.sleep(0.1)
                    else:
                        # No log file found, wait and retry
                        time.sleep(1)

    except KeyboardInterrupt:
        f.close()
        raise
    finally:
        f.close()

def main():
    parser = argparse.ArgumentParser(description='Format and display log files with pagination or follow mode.')
    parser.add_argument('-f', '--follow', action='store_true', help='Follow mode - continuously track new log entries')
    parser.add_argument('logfile', nargs='?', default=None, help='Path to the log file or directory to process (auto-detected if not provided)')
    parser.add_argument('-d', '--directory', nargs='?', default=None, help='Directory to monitor for new log files (used with -f)')

    args = parser.parse_args()

    if args.follow:
        # Follow mode
        if args.logfile:
            if os.path.isdir(args.logfile):
                # Directory provided, monitor for new files in it
                directory_path = args.logfile
                file_path = None  # Will be auto-detected
            else:
                # Specific file provided
                file_path = args.logfile
                directory_path = None
        else:
            # Auto-detect
            file_path = None
            directory_path = args.directory or find_qwen_project_dir()
            if directory_path is None:
                print("Error: Cannot find Qwen project directory.")
                sys.exit(1)

        if not os.path.exists(file_path) if file_path else True:
            # Check if directory has any .jsonl files
            test_dir = directory_path or (find_qwen_project_dir() if not args.directory else args.directory)
            if test_dir:
                jsonl_files = list(Path(test_dir).rglob("*.jsonl"))
                if not jsonl_files:
                    print(f"Error: No .jsonl files found in {test_dir}")
                    sys.exit(1)

        try:
            tail_follow(file_path=file_path, directory_path=directory_path)
        except KeyboardInterrupt:
            print("\nStopping...")
    else:
        # Normal mode - single file processing
        # Check if the provided path is a directory, or auto-detect if not provided
        if args.logfile:
            if os.path.isdir(args.logfile):
                file_path = find_latest_file(args.logfile)
            else:
                file_path = args.logfile
        else:
            # Auto-detect and find latest file
            file_path = find_latest_file()

        if not os.path.exists(file_path):
            print(f"Error: Log file {file_path} does not exist.")
            sys.exit(1)

        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()

            paginate_output(lines)
            print("End of file reached.")
        except KeyboardInterrupt:
            print("\nExiting...")

if __name__ == "__main__":
    main()