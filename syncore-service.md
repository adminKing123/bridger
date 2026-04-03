# SynCore HRMS Integration - Setup Guide

## Overview

The SynCore HRMS integration allows administrators to sync employee data from the SynCore HRMS API into the Bridger platform. This feature provides:

- **Employee Database Sync**: Fetch and sync employee data from the external HRMS API
- **Paginated Employee List**: View all employees with search and filter capabilities
- **Detailed Employee View**: View complete employee information on a dedicated page
- **Automatic Updates**: Existing employees are updated, new employees are added during sync
- **Admin Dashboard Integration**: Quick access from the admin dashboard

## Files Added

### 1. **app/services/util_syncore.py**
Utility functions for SynCore HRMS API integration:
- `get_all_employees()` - Fetch all employees from API
- `sync_employees_to_db()` - Sync employees to local database
- Base64 encoding/decoding helpers
- API request handlers

### 2. **app/models/syncore_employee.py**
Database model for storing employee information:
- Employee identifiers (user_id, employee_id)
- Personal information (name, email, gender)
- Organization details (firm, team, designation)
- Work timing and leave balances
- Sync tracking timestamps

### 3. **app/routes/admin.py** (Updated)
New admin routes:
- `GET /admin/` - Simplified admin dashboard with feature cards
- `GET /admin/users/management` - User management dashboard with stats
- `GET /admin/syncore/management` - SynCore management dashboard
- `GET /admin/syncore/employees` - Paginated employee list
- `GET /admin/syncore/employees/<id>` - Detailed employee view
- `POST /admin/syncore/sync` - Trigger employee sync

### 4. **app/templates/admin/dashboard.html** (Updated)
Simplified admin dashboard with two main feature cards:
- User Management - links to user dashboard
- SynCore Management - links to SynCore dashboard

### 5. **app/templates/admin/users_management.html**
User management dashboard template with:
- User statistics (total, verified, blocked, service access)
- Re8. **app/templates/admin/syncore_employee_detail.html**
Employee detail page template with:
- Complete employee information display
- Personal details (name, email, gender, designation)
- Organization information (firm, team, manager)
- Work schedule (reporting time, working hours)
- Leave balances (casual, emergency, comp off, extended)
- Important dates (joining, leaving, training completion)
- Sync tracking information
- Paginated table view
- View button for each employee

### 8. **app/templates/admin/syncore_employee_detail.html**
Employee detail page template with:
- Complete employee information display
- Personal details (name, email, gender, designation)
- Organization information (firm, team, manager)
- Work schedule (reporting time, working hours)
- Leave balances (casual, emergency, comp off, extended)
- Important dates (joining, leaving, training completion)
- Sync tracking information

### 6. **app/templates/admin/dashboard.html** (Updated)
Added SynCore management section to admin dashboard

## Configuration

### Environment Variables

Add the following to your `.env` file:

```bash
# SynCore HRMS Configuration (JSON format)
SYN_CORE_CONFIG='{}'
```

**Configuration Parameters:**
- `HR_CODE`: Base64-encoded HRMS authorization code
- `API_BASE`: SynCore HRMS API base URL
- `DEFAULT_USER_ID`: Default user ID for API requests
- `DEFAULT_SIGNED_ARRAY`: Default signed array for authentication
- `DATE_FMT`: Date format used by the HRMS API (default: MM/DD/YYYY)

## Database Migration

Before using the SynCore feature, you need to create the database tables:

### Using Flask-Migrate (Recommended)

If you have Flask-Migrate installed:

```bash
# Create migration
flask db migrate -m "Add SynCore employee model"

# Apply migration
flask db upgrade
```

### Manual Database Creation

If not using migrations, you can create tables manually in a Python shell:

```bash
flask shell
```

```python
from app import db
from app.models.syncore_employee import SynCoreEmployee

# Create the syncore_employees table
db.create_all()
```

## Usage

### Accessing the SynCore Admin Panel

1. Log in as a superadmin
2. Navigate to Admin Dashboard (`/admin/`)
3. Click on **"SynCore Management"** card
   - This opens the SynCore management dashboard at `/admin/syncore/management`
4. From the SynCore management page, you can:
   - Sync employee data using the "Sync Now" button
   - View all employees by clicking "View All Employees"

### Page Structure

The admin interface is organized hierarchically:

- **Admin Dashboard** (`/admin/`) - Main landing page with feature cards
  - **User Management** (`/admin/users/management`) - User statistics and overview
    - **Users List** (`/admin/users`) - Paginated user list
      - **User Detail** (`/admin/users/<id>`) - Individual user profile
  - **SynCore Management** (`/admin/syncore/management`) - SynCore dashboard with sync controls
    - **Employee List** (`/admin/syncore/employees`) - Paginated employee list
      - **Employee Detail** (`/admin/syncore/employees/<id>`) - Individual employee profile

### Syncing Employees

1. Navigate to SynCore Management page (`/admin/syncore/management`)
2. Click the **"Sync Now"** button in the Employee Sync card
3. The system will:
   - Fetch all employees from the HRMS API
   - Update existing employees with new data
   - Add new employees to the database
4. View sync statistics (added, updated, total) in the success message
5. The page will refresh to show updated statistics

### Searching and Filtering

- **Search**: Use the search box to find employees by:
  - Name
  - Email
  - Employee ID
  - Designation

- **Filters**: Use status tabs to filter by:
  - All employees
  - Active employees only
  - Inactive employees only

### Viewing Employee Details

Click the **eye icon** next to any employee in the list to view their complete information:

- **Personal Information**: Name, email, gender, designation, user type
- **Organization Details**: Firm name, organization, team lead, manager status
- **Work Schedule**: Reporting time, working hours, monthly worklog hours
- **Leave Balances**: Casual leave, emergency leave, comp off, extended leave
- **Important Dates**: Joining date, leaving date, training completion
- **Additional Details**: SynCoin, overrides, created/modified by
- **Sync Information**: Last synced time, signed array

### Employee Data Fields

The following data is synced for each employee:

- **Identifiers**: User ID, Employee ID, Signed Array
- **Personal**: Name, Email, Gender
- **Organization**: Firm Name, Organization Name, Team Lead
- **Position**: Designation, User Type (Employee/Intern)
- **Dates**: Joining Date, Leaving Date, Training Completion
- **Leave Balances**: Comp Off, Emergency Leave, Casual Leave, Extended Leave
- **Work Details**: Reporting Time, Working Hours, Monthly Worklog Hours
- **Status**: Active/Inactive

## API Response Format

The HRMS API returns employee data in the following format:

```json
{
  "user_id": "630",
  "employee_id": "1561",
  "name": "John Doe",
  "firm_id": "15",
  "username": "john.doe@company.com",
  "gender": "Male",
  "reporting_time": "10:00",
  "org_team_id": "10",
  "team_lead_id": "47",
  "designation": "Software Engineer",
  "user_type": "Employee",
  "status": "Active",
  "joining_date": "01/15/2024",
  "leaving_date": null,
  "firm_name": "Company Name",
  "org_name": "Engineering",
  "team_lead": "Jane Smith",
  // ... additional fields
}
```

## Troubleshooting

### Sync Fails

1. **Check API Configuration**: Ensure `SYN_CORE_CONFIG` is properly set in `.env`
2. **Check Logs**: Review application logs for error details
3. **API Connectivity**: Verify network access to the HRMS API endpoint
4. **Authentication**: Ensure HR_CODE and SIGNED_ARRAY are valid

### No Employees Showing

1. **Run Sync**: Click "Sync Now" to fetch employee data
2. **Check Database**: Verify the `syncore_employees` table exists
3. **Review Sync Stats**: Check for sync errors in flash messages

### Database Errors

1. **Missing Table**: Run database migrations (see Database Migration section)
2. **Column Errors**: Ensure you're running the latest code version
3. **Constraint Violations**: Check for duplicate employee IDs

## Security Notes

- Only superadmins can access SynCore management
- API credentials are stored as environment variables
- Sensitive data is not logged
- CSRF protection is enabled on all sync operations

## Future Enhancements

Potential improvements for the SynCore integration:

- [ ] Scheduled automatic sync (cron job)
- [ ] Export employee data to CSV/Excel
- [ ] Department and team hierarchies visualization
- [ ] Integration with Bridger user accounts
- [ ] Attendance and leave tracking
- [ ] Workforce analytics and reports
- [ ] Employee search by department/team
- [ ] Historical sync logs and audit trail

## Support

For issues or questions about the SynCore integration:

1. Check application logs for error details
2. Verify environment configuration
3. Review API documentation
4. Contact system administrator
