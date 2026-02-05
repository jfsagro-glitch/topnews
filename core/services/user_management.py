"""
User and invite management for sandbox environment
"""
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class UserInviteManager:
    """Manage sandbox user access and invites"""
    
    def __init__(self, db):
        self.db = db
    
    def get_approved_users(self):
        """Get list of approved users"""
        try:
            users_data = self.db.get_feature_flag(None, 'sandbox_approved_users', None)
            if users_data:
                return json.loads(users_data) if isinstance(users_data, str) else users_data
            return []
        except Exception as e:
            logger.error(f"Error getting approved users: {e}")
            return []
    
    def get_pending_invites(self):
        """Get list of pending invites"""
        try:
            invites_data = self.db.get_feature_flag(None, 'sandbox_pending_invites', None)
            if invites_data:
                return json.loads(invites_data) if isinstance(invites_data, str) else invites_data
            return []
        except Exception as e:
            logger.error(f"Error getting pending invites: {e}")
            return []
    
    def add_approved_user(self, user_id: int):
        """Add user to approved list"""
        try:
            users = self.get_approved_users()
            if user_id not in users:
                users.append(user_id)
                self.db.set_feature_flag(None, 'sandbox_approved_users', json.dumps(users))
                logger.info(f"Added user {user_id} to approved list")
                return True
            return False
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def remove_approved_user(self, user_id: int):
        """Remove user from approved list"""
        try:
            users = self.get_approved_users()
            if user_id in users:
                users.remove(user_id)
                self.db.set_feature_flag(None, 'sandbox_approved_users', json.dumps(users))
                logger.info(f"Removed user {user_id} from approved list")
                return True
            return False
        except Exception as e:
            logger.error(f"Error removing user: {e}")
            return False
    
    def create_invite(self) -> str:
        """Create new invite code"""
        try:
            import uuid
            invite_code = str(uuid.uuid4())[:8].upper()
            invites = self.get_pending_invites()
            
            # Store invite with creation time
            invite_entry = {
                "code": invite_code,
                "created": datetime.now().isoformat(),
                "used": False
            }
            invites.append(invite_entry)
            self.db.set_feature_flag(None, 'sandbox_pending_invites', json.dumps(invites))
            logger.info(f"Created invite code: {invite_code}")
            return invite_code
        except Exception as e:
            logger.error(f"Error creating invite: {e}")
            return None
    
    def use_invite(self, invite_code: str, user_id: int) -> bool:
        """Use invite code to add user"""
        try:
            invites = self.get_pending_invites()
            for invite in invites:
                if invite.get("code") == invite_code and not invite.get("used"):
                    # Mark as used
                    invite["used"] = True
                    invite["used_by"] = user_id
                    invite["used_at"] = datetime.now().isoformat()
                    self.db.set_feature_flag(None, 'sandbox_pending_invites', json.dumps(invites))
                    
                    # Add user to approved
                    self.add_approved_user(user_id)
                    logger.info(f"User {user_id} used invite {invite_code}")
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error using invite: {e}")
            return False
    
    def revoke_invite(self, invite_code: str) -> bool:
        """Revoke an invite code"""
        try:
            invites = self.get_pending_invites()
            for i, invite in enumerate(invites):
                if invite.get("code") == invite_code and not invite.get("used"):
                    invites.pop(i)
                    self.db.set_feature_flag(None, 'sandbox_pending_invites', json.dumps(invites))
                    logger.info(f"Revoked invite {invite_code}")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error revoking invite: {e}")
            return False
