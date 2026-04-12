# Ticket System

This is a ticket system that allows users to create, manage, and track tickets for various issues and tasks. The system is designed to simplify the ticketing process and improve workflow efficiency.

## Features
- Create and manage tickets
- Assign tickets to users
- Track ticket status and history

## Installation
1. Clone the repository: `git clone https://github.com/ChristopherFibich/TicketSystem.git`
2. Navigate to the project directory: `cd TicketSystem`
3. Install dependencies: `npm install`

## Usage
Run the application: `npm start`

## Systemd Service

### Ticket System Service

This section describes how to set up the Ticket System as a systemd service:

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/ticket-system.service
   ```

2. Add the following content to the service file:
   ```ini
   [Unit]
   Description=Ticket System Service
   After=network.target

   [Service]
   ExecStart=/usr/bin/node /path/to/your/app.js
   Restart=always
   User=nobody
   Environment=PATH=/usr/bin:/usr/local/bin
   Environment=NODE_ENV=production

   [Install]
   WantedBy=multi-user.target
   ```

3. Reload systemd to apply the changes:
   ```bash
   sudo systemctl daemon-reload
   ```

4. Start the Ticket System service:
   ```bash
   sudo systemctl start ticket-system
   ```

5. Enable the service to start on boot:
   ```bash
   sudo systemctl enable ticket-system
   ```

Follow these steps to successfully set up and run the Ticket System as a service on your system.
