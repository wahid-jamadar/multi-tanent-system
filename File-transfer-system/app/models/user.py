from app.extensions import db, utcnow

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(100), primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_login_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    organization_id = db.Column(db.String(100), db.ForeignKey('organizations.id'), nullable=True)
    roles = db.relationship('Role', secondary='user_roles', backref='users')
    organization = db.relationship('Organization', backref=db.backref('users', cascade='all, delete-orphan'))

class UserRole(db.Model):
    __tablename__ = 'user_roles'
    user_id = db.Column(db.String(100), db.ForeignKey('users.id'), primary_key=True)
    role_id = db.Column(db.BigInteger, db.ForeignKey('roles.id'), primary_key=True)
