from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, current_app
from flask_login import login_required, current_user
from flask_socketio import SocketIO, join_room, leave_room
from app import db, socketio
from app.models import User, Location, Conversation, Message, Notification
from datetime import datetime, UTC
from werkzeug.utils import secure_filename
import os

messages_bp = Blueprint('messages', __name__)

def get_team_lead_for_region(region_id):
    """Récupère le team_lead d'une région donnée."""
    return User.query.filter_by(role='team_lead', location_id=region_id).first()

def can_access_conversation(user, conversation):
    """Vérifie si l'utilisateur peut accéder à la conversation."""
    if conversation.type == 'private':
        messages = Message.query.filter_by(conversation_id=conversation.id).all()
        if not messages:
            return False
        
        participants = set()
        senders = {msg.sender_id for msg in messages}
        
        for sender_id in senders:
            sender = User.query.get(sender_id)
            if not sender:
                continue
                
            participants.add(sender.id)
            
            if sender.role == 'data_entry':
                district = sender.location
                if district and district.type == 'DIS':
                    region = district.parent
                    if region:
                        team_lead = get_team_lead_for_region(region.id)
                        if team_lead:
                            participants.add(team_lead.id)
            
            elif sender.role == 'team_lead':
                region = sender.location
                if region and region.type == 'REG':
                    districts = Location.query.filter_by(parent_id=region.id, type='DIS').all()
                    data_entries = User.query.filter(
                        User.location_id.in_([d.id for d in districts]),
                        User.role == 'data_entry'
                    ).all()
                    for data_entry in data_entries:
                        participants.add(data_entry.id)
                
                data_viewers = User.query.filter_by(role='data_viewer').all()
                for dv in data_viewers:
                    participants.add(dv.id)
            
            elif sender.role == 'data_viewer':
                team_leads = User.query.filter_by(role='team_lead').all()
                for tl in team_leads:
                    participants.add(tl.id)
        
        return user.id in participants

    elif conversation.type == 'group':
        if conversation.title == 'Groupe Global des Team Leads':
            return user.role in ['team_lead', 'data_viewer']
        else:
            region = conversation.location
            if not region or region.type != 'REG':
                return False
            if user.role == 'data_viewer':
                return True
            if user.role == 'team_lead' and user.location_id == region.id:
                return True
            if user.role == 'data_entry':
                user_district = user.location
                if user_district and user_district.type == 'DIS':
                    user_region = user_district.parent
                    return user_region and user_region.id == region.id
    return False

def get_user_conversations(user):
    """Récupère et initialise les conversations accessibles pour l'utilisateur."""
    conversations = []

    if user.role == 'data_entry':
        district = user.location
        if district and district.type == 'DIS':
            region = district.parent
            if region:
                team_lead = get_team_lead_for_region(region.id)
                if team_lead:
                    conversation = get_or_create_private_conversation(user, team_lead)
                    if conversation:
                        conversations.append(conversation)

    elif user.role == 'team_lead':
        region = user.location
        if region and region.type == 'REG':
            for data_entry in get_region_data_entries(region.id):
                conversation = get_or_create_private_conversation(user, data_entry)
                if conversation:
                    conversations.append(conversation)

            for data_viewer in User.query.filter_by(role='data_viewer').all():
                conversation = get_or_create_private_conversation(user, data_viewer)
                if conversation:
                    conversations.append(conversation)

    elif user.role == 'data_viewer':
        for team_lead in User.query.filter_by(role='team_lead').all():
            conversation = get_or_create_private_conversation(user, team_lead)
            if conversation:
                conversations.append(conversation)

    for region in Location.query.filter_by(type='REG').all():
        conversation = get_or_create_group_conversation(region)
        if can_access_conversation(user, conversation):
            conversations.append(conversation)

    global_group = get_or_create_global_team_lead_group()
    if can_access_conversation(user, global_group):
        conversations.append(global_group)

    return conversations

def get_or_create_private_conversation(user1, user2):
    """Trouve ou crée une conversation privée entre deux utilisateurs."""
    conversation = Conversation.query.filter_by(type='private').join(Message).filter(
        (Message.sender_id == user1.id) | (Message.sender_id == user2.id)
    ).group_by(Conversation.id).having(db.func.count(Message.id) > 0).first()

    if not conversation:
        conversation = Conversation(type='private')
        db.session.add(conversation)
        db.session.flush()
        initial_message = Message(
            conversation_id=conversation.id,
            sender_id=user1.id,
            content="Conversation initiée",
            timestamp=datetime.now(UTC),
            read=False
        )
        db.session.add(initial_message)
        db.session.commit()
    return conversation

def get_or_create_group_conversation(region):
    """Trouve ou crée une conversation de groupe pour une région."""
    conversation = Conversation.query.filter_by(type='group', location_id=region.id).first()
    if not conversation:
        conversation = Conversation(type='group', location_id=region.id)
        db.session.add(conversation)
        db.session.commit()
    return conversation

def get_or_create_global_team_lead_group():
    """Trouve ou crée le groupe global des team leads."""
    conversation = Conversation.query.filter_by(type='group', title='Groupe Global des Team Leads').first()
    if not conversation:
        conversation = Conversation(type='group', title='Groupe Global des Team Leads')
        db.session.add(conversation)
        db.session.commit()
    return conversation

def get_region_data_entries(region_id):
    """Récupère tous les data_entries d'une région."""
    districts = Location.query.filter_by(parent_id=region_id, type='DIS').all()
    return User.query.filter(User.location_id.in_([d.id for d in districts]), User.role == 'data_entry').all()

@messages_bp.route('/messages')
@login_required
def index():
    """Affiche la liste des conversations avec dernières infos."""
    conversations = get_user_conversations(current_user)
    conversations_data = []
    
    for conversation in conversations:
        last_message = Message.query.filter_by(conversation_id=conversation.id).order_by(Message.timestamp.desc()).first()
        message_ids = [msg.id for msg in Message.query.filter_by(conversation_id=conversation.id).all()]
        unread_count = Notification.query.filter(
            Notification.user_id == current_user.id,
            Notification.read == False,
            Notification.message_id.in_(message_ids)
        ).count()
        
        conversations_data.append({
            'conversation': conversation,
            'last_message': last_message,
            'unread_count': unread_count
        })
    
    return render_template('messages/index.html', conversations_data=conversations_data)

@messages_bp.route('/conversation/<int:conversation_id>')
@login_required
def conversation(conversation_id):
    """Affiche une conversation spécifique."""
    conversation = Conversation.query.get_or_404(conversation_id)
    
    if not can_access_conversation(current_user, conversation):
        flash("Accès non autorisé à cette conversation.", 'danger')
        return redirect(url_for('messages.index'))

    # Marquer les messages comme lus
    messages = Message.query.filter_by(conversation_id=conversation_id).all()
    for message in messages:
        if message.sender_id != current_user.id and not message.read:
            message.read = True
    db.session.commit()

    # Marquer les notifications comme lues
    message_ids = [msg.id for msg in messages]
    Notification.query.filter(
        Notification.user_id == current_user.id,
        Notification.read == False,
        Notification.message_id.in_(message_ids)
    ).update({'read': True})
    db.session.commit()

    other_user = None
    if conversation.type == 'private':
        first_message = messages[0] if messages else None
        if first_message:
            other_user = first_message.sender if first_message.sender.id != current_user.id else None
            if not other_user and len(messages) > 1:
                for msg in messages[1:]:
                    if msg.sender.id != current_user.id:
                        other_user = msg.sender
                        break

    return render_template('messages/conversation.html', 
                         conversation=conversation, 
                         messages=messages,
                         other_user=other_user)

@messages_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    """Envoie un message dans une conversation."""
    conversation_id = request.form.get('conversation_id')
    content = request.form.get('content', '').strip()
    file = request.files.get('file')
    print(f"Received form data: conversation_id={conversation_id}, content={content}, file={file}")  # Debug

    conversation = Conversation.query.get_or_404(conversation_id)
    
    if not can_access_conversation(current_user, conversation):
        flash("Accès non autorisé.", 'danger')
        return redirect(url_for('messages.index'))

    if not content and not file:
        flash("Message vide non autorisé.", 'danger')
        return redirect(url_for('messages.conversation', conversation_id=conversation.id))

    attachment_path, attachment_type = handle_file_upload(file, conversation.id) if file else (None, None)
    print(f"After handle_file_upload: attachment_path={attachment_path}, attachment_type={attachment_type}")  # Debug

    message = create_message(conversation, content, attachment_path, attachment_type)
    create_notifications(conversation, message)

    db.session.commit()

    # Emit SocketIO event for new message
    socketio.emit('new_message', {
        'content': message.content,
        'sender': current_user.name,
        'timestamp': message.timestamp.strftime('%H:%M'),
        'attachment_path': message.attachment_path,
        'attachment_type': message.attachment_type,
        'conversation_id': str(conversation.id)
    }, room=str(conversation_id))

    flash("Message envoyé.", 'success')
    return redirect(url_for('messages.conversation', conversation_id=conversation.id))

def allowed_file(filename):
    """Vérifie si le fichier a une extension autorisée."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def handle_file_upload(file, conversation_id):
    """Gère l'upload de fichier et retourne le chemin et type."""
    if file:
        print(f"File received: {file.filename}, allowed_extensions={current_app.config['ALLOWED_EXTENSIONS']}")  # Debug
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now(UTC).strftime('%Y%m%d_%H%M%S')
            unique_filename = f"message_{conversation_id}_{timestamp}_{filename}"
            file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            print(f"Saving file to {file_path}")  # Debug
            try:
                file.save(file_path)
                print(f"File saved: {os.path.exists(file_path)}")  # Debug
                if not os.path.exists(file_path):
                    print(f"Error: File not found after saving at {file_path}")  # Debug
                    flash("Erreur : le fichier n'a pas pu être enregistré.", 'danger')
                    return None, None
                
                ext = filename.rsplit('.', 1)[1].lower()
                attachment_type = 'image' if ext in {'png', 'jpg', 'jpeg', 'gif'} else 'video' if ext == 'mp4' else 'file'
                
                return f"uploads/messages/{unique_filename}", attachment_type
            except Exception as e:
                print(f"Error saving file: {str(e)}")  # Debug
                flash(f"Erreur lors de l'enregistrement du fichier : {str(e)}", 'danger')
                return None, None
        else:
            print(f"File extension not allowed: {file.filename}")  # Debug
            flash(f"Type de fichier non autorisé : {file.filename}. Types autorisés : {', '.join(current_app.config['ALLOWED_EXTENSIONS'])}", 'danger')
            return None, None
    else:
        print("No file received")  # Debug
        flash("Aucun fichier reçu. Veuillez sélectionner un fichier.", 'danger')
    return None, None

def create_message(conversation, content, attachment_path, attachment_type):
    """Crée et retourne un nouveau message."""
    message = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        content=content if content else None,
        timestamp=datetime.now(UTC),
        attachment_path=attachment_path,
        attachment_type=attachment_type,
        read=False
    )
    db.session.add(message)
    db.session.flush()
    return message

def create_notifications(conversation, message):
    """Crée les notifications pour les participants."""
    if conversation.type == 'private':
        participants = {msg.sender_id for msg in Message.query.filter_by(conversation_id=conversation.id).all()}
        participants.discard(current_user.id)
        for user_id in participants:
            db.session.add(Notification(
                user_id=user_id,
                message_id=message.id,
                notification_message=f"Nouveau message de {current_user.name}",
                created_at=datetime.now(UTC),
                read=False
            ))
    else:
        if conversation.title == 'Groupe Global des Team Leads':
            users = User.query.filter(
                User.role.in_(['team_lead', 'data_viewer']),
                User.id != current_user.id
            ).all()
        else:
            region = conversation.location
            districts = Location.query.filter_by(parent_id=region.id, type='DIS').all()
            users = User.query.filter(
                (User.location_id == region.id) | 
                (User.location_id.in_([d.id for d in districts])) | 
                (User.role == 'data_viewer'),
                User.id != current_user.id
            ).all()

        group_name = conversation.location.name if conversation.location else conversation.title
        for user in users:
            db.session.add(Notification(
                user_id=user.id,
                message_id=message.id,
                notification_message=f"Nouveau message dans {group_name}",
                created_at=datetime.now(UTC),
                read=False
            ))

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room(str(current_user.id))

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(str(current_user.id))

@socketio.on('join')
def handle_join(data):
    conversation_id = data['conversation_id']
    join_room(conversation_id)