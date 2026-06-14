# User Role and Access Control Changes

Based on the required page-by-page mapping, the following changes are implemented for the roles: `super_admin`, `organization_admin`, and `organization_viewer`.

## Access Mapping Table

| Page | Super Admin (`super_admin`) | Org Admin (`organization_admin`) | Viewer (`organization_viewer`) |
| :--- | :--- | :--- | :--- |
| **Dashboard** | Full access | Own org only | Own org only |
| **Organizations** | Full access | No | No |
| **Agents** | View/edit/delete all | View/edit/delete own org | View only |
| **Scripts** | View/edit/delete all | View/edit/delete own org | View only |
| **Script Management** | Full access | Own org only | View only or hide |
| **Logs** | All logs | Own org logs | Own org logs |
| **Alerts** | All alerts, delete/clear | Own org alerts, maybe acknowledge only | View only |
| **Backups** | All org backups | Own org backups only | No |
| **Settings** | Global settings | No | No |
| **Users** | All users | Own org users only | View own profile only |
| **Admin Logs** | Full access | No | No |
| **Profile** | Own profile | Own profile | Own profile |

## Implementation Plan

1. **Dashboard (`/`, `/dashboard`)**: Both Org Admin and Viewer have access to their own org data. (Already mostly implemented via `filter_by_org`).
2. **Organizations (`/organizations`)**: Restrict to Super Admin only.
3. **Agents (`/agents`)**: Viewer can only view agents, no edit/delete. Org admin can view/edit/delete in own org. Super admin has full access.
4. **Scripts (`/scripts`)**: Viewer can only view scripts, no edit/delete. Org admin can view/edit/delete in own org. Super admin has full access.
5. **Script Management (`/scripts_management` or similar)**: Restrict Viewer (hide UI elements). Full access to Super Admin, Org Admin (own org).
6. **Logs (`/logs`)**: Org Admin and Viewer access own org logs. (Mostly implemented).
7. **Alerts (`/alerts`)**: Viewer can only view alerts. Org Admin can acknowledge. Super admin can delete/clear.
8. **Backups (`/backup` or similar)**: Viewer has no access. Org Admin has access to own org backups. Super admin has full access.
9. **Settings (`/settings`)**: Restrict to Super Admin only.
10. **Users (`/users`)**: Viewer can only view own profile. Org Admin can view/edit users in own org. Super admin has full access.
11. **Admin Logs (`/admin_logs`)**: Restrict to Super Admin only.
12. **Profile (`/profile`)**: All users have access to their own profile.

These access control checks will be enforced both on the backend (`server.py` routes) and the frontend (hiding/disabling buttons in HTML templates based on the user's role).
