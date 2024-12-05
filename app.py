from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import paramiko
import socket

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Needed for flashing messages

# Load credentials from JSON file
with open('credentials.json', 'r') as file:
    credentials = json.load(file)

VALID_USERNAME = credentials['username']
VALID_PASSWORD = credentials['password']

# List of servers
servers = credentials['servers']

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Compare username case-insensitively
        if username.lower() == VALID_USERNAME.lower() and password == VALID_PASSWORD:
            return redirect(url_for('dashboard', username=username))
        else:
            flash('Invalid credentials, please try again.')
            return redirect(url_for('login'))

    return render_template('base.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', servers=servers)

@app.route('/connect', methods=['POST'])
def connect():
    server_ip = request.form.get('server')
    
    # Find server details
    server_details = next((server for server in servers if server['ip'] == server_ip), None)
    
    if not server_details:
        return jsonify({'success': False, 'message': 'Server not found'})
    
    try:
        # Initialize SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Attempt connection with timeout
        ssh.connect(
            hostname=server_details['ip'],
            username=server_details['targetPCName'],
            password=server_details['targetPCPassword'],
            timeout=5
        )
        
        # Test connection with simple command
        ssh.exec_command('echo "Connected"')
        
        # Execute all PowerShell commands
        processes = []
        for ps_command in credentials['powershellCommands']:
            # Properly escape the PowerShell command
            powershell_cmd = f'powershell.exe -Command "{ps_command["command"]}"'
            stdin, stdout, stderr = ssh.exec_command(powershell_cmd)
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            if error:
                return jsonify({
                    'success': True, 
                    'message': f'Connected to {server_details["name"]}, but command {ps_command["name"]} failed: {error}'
                })

            # Parse the PowerShell output into a list of processes
            lines = output.strip().split('\n')
            
            # Skip the header and separator lines
            data_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith('---')]
            if len(data_lines) > 1:  # Skip header line
                data_lines = data_lines[1:]
            
            for line in data_lines:
                parts = line.strip().split(None)  # Split on any whitespace
                if len(parts) >= 2:  # As long as we have at least process ID and name
                    try:
                        process_name = parts[-1]  # Last part is the process name
                        process_id = next((part for part in reversed(parts[:-1]) if part.isdigit()), "N/A")
                        processes.append({
                            'name': process_name,
                            'id': process_id,
                            'command_name': ps_command["name"]  # Add which command found this process
                        })
                    except Exception as e:
                        print(f"Error parsing line: {line} - {str(e)}")
                        continue

        return jsonify({
            'success': True,
            'message': f'Connected to {server_details["name"]} successfully',
            'processes': processes
        })
        
    except (paramiko.AuthenticationException, paramiko.SSHException) as e:
        return jsonify({'success': False, 'message': f'Authentication failed: {str(e)}'})
    except socket.timeout:
        return jsonify({'success': False, 'message': 'Connection timed out'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Connection failed: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True)
