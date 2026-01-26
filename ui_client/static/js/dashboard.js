// Dashboard JavaScript for SalesShortcut UI Client

class DashboardManager {
    constructor() {
        this.websocket = null;
        this.reconnectInterval = null;
        this.businesses = new Map();
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        this.initializeWebSocket();
        this.initializeEventListeners();
        this.updateStats();
    }
    
    initializeWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        try {
            this.websocket = new WebSocket(wsUrl);
            this.setupWebSocketHandlers();
        } catch (error) {
            console.error('Failed to create WebSocket connection:', error);
            this.scheduleReconnect();
        }
    }
    
    setupWebSocketHandlers() {
        this.websocket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus(true);
            
            if (this.reconnectInterval) {
                clearInterval(this.reconnectInterval);
                this.reconnectInterval = null;
            }
        };
        
        this.websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        this.websocket.onclose = () => {
            console.log('WebSocket disconnected');
            this.isConnected = false;
            this.updateConnectionStatus(false);
            this.scheduleReconnect();
        };
        
        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.updateConnectionStatus(false);
        };
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnection attempts reached');
            return;
        }
        
        if (this.reconnectInterval) {
            return; // Already scheduled
        }
        
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
        console.log(`Scheduling reconnect in ${delay}ms`);
        
        this.reconnectInterval = setTimeout(() => {
            this.reconnectAttempts++;
            this.initializeWebSocket();
        }, delay);
    }
    
    handleWebSocketMessage(data) {
        console.log('Received WebSocket message:', data);
        console.log('Message type is:', data.type, 'Type of:', typeof data.type);
        
        switch (data.type) {
            case 'initial_state':
                this.handleInitialState(data);
                break;
            case 'business_added':
                this.handleBusinessAdded(data);
                break;
            case 'business_updated':
                this.handleBusinessUpdated(data);
                break;
            case 'process_started':
                this.handleProcessStarted(data);
                break;
            case 'lead_finding_completed':
                this.handleLeadFindingCompleted(data);
                break;
            case 'lead_finding_failed':
                this.handleLeadFindingFailed(data);
                break;
            case 'lead_finding_empty':
                this.handleLeadFindingEmpty(data);
                break;
            case 'process_finished':
                this.handleProcessFinished(data);
                break;
            case 'state_reset':
                this.handleStateReset(data);
                break;
            case 'sdr_engaged':
                this.handleSdrEngaged(data);
                break;
            case 'lead_confirmed':
                this.handleLeadConfirmed(data);
                break;
            case 'lead_rejected':
                this.handleLeadRejected(data);
                break;
            case 'human_input_request':
                console.log('Matched human_input_request case!');
                this.handleHumanInputRequest(data);
                break;
            case 'human_input_response_submitted':
                this.handleHumanInputResponseSubmitted(data);
                break;
            case 'calendar_notification':
                this.handleCalendarNotification(data);
                break;
            case 'meeting_scheduled':
                this.handleMeetingScheduled(data);
                break;
            default:
                console.log('Unknown message type:', data.type);
        }
    }
    
    handleInitialState(data) {
        console.log('Loading initial state:', data);
        
        // Clear existing businesses
        this.businesses.clear();
        
        // Load businesses
        if (data.businesses) {
            data.businesses.forEach(business => {
                this.businesses.set(business.id, business);
            });
        }
        
        // Update UI
        this.updateStats();
        this.updateAgentStatuses(data.is_running);
        
        // Don't close human input dialog on initial state - it might be legitimate state refresh
        // Only close dialog if it was just submitted (check for success message)
    }
    
    handleBusinessAdded(data) {
        console.log('Business added:', data.business);
        
        this.businesses.set(data.business.id, data.business);
        this.addBusinessCard(data.business, data.agent);
        this.updateStats();
        this.addActivityLogEntry(data.agent, `Found business: ${data.business.name}`, data.timestamp);
        this.updateAgentStatus(data.agent, true);
    }
    
    handleBusinessUpdated(data) {
        console.log('Business updated:', data.business);
        
        const oldBusiness = this.businesses.get(data.business.id);
        this.businesses.set(data.business.id, data.business);
        
        if (!oldBusiness) {
            // This is a new business, create a new card
            console.log('Creating new business card for:', data.business.name);
            this.addBusinessCard(data.business, data.agent);
        } else if (oldBusiness.status !== data.business.status) {
            // Status changed, move the card
            console.log('Moving business card due to status change:', data.business.name);
            this.moveBusinessCard(data.business, oldBusiness.status, data.business.status);
        } else {
            // Update existing card
            this.updateBusinessCard(data.business);
        }
        
        this.updateStats();
        this.addActivityLogEntry(
            data.agent, 
            `Updated ${data.business.name}: ${data.update.message}`, 
            data.timestamp
        );
        this.updateAgentStatus(data.agent, true);
    }
    
    handleProcessStarted(data) {
        console.log('Process started for city:', data.city);
        this.showLoadingOverlay();
        this.updateAgentStatus('lead_finder', true);
        this.addActivityLogEntry('system', `Started lead finding for ${data.city}`, data.timestamp);
    }
    
    handleLeadFindingCompleted(data) {
        console.log('Lead finding completed:', data);
        this.hideLoadingOverlay();
        this.updateAgentStatus('lead_finder', false);
        this.addActivityLogEntry(
            'lead_finder', 
            `Found ${data.business_count} businesses in ${data.city}`, 
            data.timestamp
        );
    }
    
    handleLeadFindingFailed(data) {
        console.log('Lead finding failed:', data);
        this.hideLoadingOverlay();
        this.updateAgentStatus('lead_finder', false);
        this.addActivityLogEntry('lead_finder', `Error: ${data.error}`, data.timestamp);
        this.showErrorToast(data.error);
    }
    
    handleLeadFindingEmpty(data) {
        console.log('Lead finding empty:', data);
        this.addActivityLogEntry('lead_finder', data.message, data.timestamp);
        // No error toast for empty results - this is normal behavior
    }
    
    handleProcessFinished(data) {
        console.log('Process finished:', data);
        // Any final cleanup can be done here
    }
    
    handleStateReset(data) {
        console.log('State reset');
        this.businesses.clear();
        this.clearAllBusinessCards();
        this.updateStats();
        this.updateAgentStatuses(false);
        this.addActivityLogEntry('system', 'Dashboard reset', data.timestamp);
    }
    
    addBusinessCard(business, agent) {
        const column = this.getColumnForStatus(business.status);
        if (!column) return;
        
        const content = column.querySelector('.column-content');
        const card = this.createBusinessCard(business);
        
        // Add with animation
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        content.appendChild(card);
        
        // Trigger animation
        requestAnimationFrame(() => {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        });
    }
    
    updateBusinessCard(business) {
        const existingCard = document.querySelector(`[data-business-id="${business.id}"]`);
        if (!existingCard) return;
        
        const newCard = this.createBusinessCard(business);
        existingCard.parentNode.replaceChild(newCard, existingCard);
    }
    
    moveBusinessCard(business, oldStatus, newStatus) {
        const existingCard = document.querySelector(`[data-business-id="${business.id}"]`);
        if (!existingCard) {
            // Card doesn't exist, create new one
            this.addBusinessCard(business, this.getAgentForStatus(newStatus));
            return;
        }
        
        const newColumn = this.getColumnForStatus(newStatus);
        if (!newColumn) return;
        
        const newContent = newColumn.querySelector('.column-content');
        
        // Remove from old location
        existingCard.remove();
        
        // Create new card in new location
        const newCard = this.createBusinessCard(business);
        newCard.style.opacity = '0';
        newCard.style.transform = 'translateY(20px)';
        newContent.appendChild(newCard);
        
        // Animate in
        requestAnimationFrame(() => {
            newCard.style.transition = 'all 0.3s ease';
            newCard.style.opacity = '1';
            newCard.style.transform = 'translateY(0)';
        });
    }
    
    createBusinessCard(business) {
        const card = document.createElement('div');
        const isHotLead = business.status === 'converting';
        const isMeeting = business.status === 'meeting_scheduled';
        const isPending = business.status === 'pending';
        const isConfirmed = business.status === 'confirmed';
        const isSdrEngaged = business.status === 'sdr_engaged';
        const isClickable = business.status === 'found'; // Only "found" businesses can be clicked for research
        
        card.className = `business-card compact ${isMeeting ? 'meeting-card' : ''} ${isHotLead ? 'hot-lead' : ''} ${isPending ? 'pending-card' : ''} ${isClickable ? 'clickable' : ''}`;
        card.setAttribute('data-business-id', business.id);
        
        // Add click handler for "found" status businesses - now opens research dialog first
        if (isClickable) {
            card.addEventListener('click', () => {
                this.showResearchDialog(business);
            });
        }
        
        // Add click handler for SDR engaged or pending businesses - show email draft
        if (isSdrEngaged || isPending) {
            card.addEventListener('click', () => {
                this.showEmailDraftDialog(business);
            });
            card.style.cursor = 'pointer';
        }
        
        const statusText = this.getStatusText(business.status);
        // For meeting_scheduled status, use 'meeting' class to match CSS
        const statusClass = isMeeting ? 'meeting' : isPending ? 'pending' : isConfirmed ? 'confirmed' : business.status.replace('_', '-');
        
        // Create compact notes if available
        let compactNotesHtml = '';
        if (business.notes && business.notes.length > 0) {
            const lastNote = business.notes[business.notes.length - 1];
            const truncatedNote = lastNote.length > 50 ? lastNote.substring(0, 50) + '...' : lastNote;
            const noteIcon = isMeeting ? 'fas fa-calendar-check' : 'fas fa-sticky-note';
            compactNotesHtml = `
                <div class="compact-notes">
                    <i class="${noteIcon}"></i>
                    <span>${this.escapeHtml(truncatedNote)}</span>
                </div>
            `;
        }
        
        // Create contact row
        let contactRowHtml = '';
        const contactItems = [];
        if (business.phone) {
            contactItems.push(`<div class="contact-item"><i class="fas fa-phone"></i><span>${this.escapeHtml(business.phone)}</span></div>`);
        }
        if (business.email) {
            const truncatedEmail = business.email.length > 20 ? business.email.substring(0, 20) + '...' : business.email;
            contactItems.push(`<div class="contact-item"><i class="fas fa-envelope"></i><span>${this.escapeHtml(truncatedEmail)}</span></div>`);
        }
        if (contactItems.length > 0) {
            contactRowHtml = `<div class="contact-row">${contactItems.join('')}</div>`;
        }
        
        // Create business title with icon for special statuses
        let businessTitleHtml = '';
        if (isHotLead) {
            businessTitleHtml = `
                <div class="business-title">
                    <i class="fas fa-fire hot-icon"></i>
                    <h4>${this.escapeHtml(business.name)}</h4>
                </div>
            `;
        } else if (isMeeting) {
            businessTitleHtml = `
                <div class="business-title">
                    <i class="fas fa-handshake meeting-icon"></i>
                    <h4>${this.escapeHtml(business.name)}</h4>
                </div>
            `;
        } else {
            businessTitleHtml = `<h4>${this.escapeHtml(business.name)}</h4>`;
        }
        
        // Adjust status text for compact display
        const compactStatusText = isMeeting ? 'Meeting' : statusText;
        
        // Add manual confirm button for pending leads
        let pendingActionsHtml = '';
        if (isPending) {
            pendingActionsHtml = `
                <div class="pending-actions" style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #e0e0e0; display: flex; gap: 8px;">
                    <button class="btn-confirm-lead" onclick="event.stopPropagation(); dashboardManagerInstance.manualConfirmLead('${business.id}')" 
                        style="flex: 1; padding: 8px 12px; background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 5px;">
                        <i class="fas fa-check"></i> Confirm Lead
                    </button>
                    <button class="btn-check-email" onclick="event.stopPropagation(); dashboardManagerInstance.checkEmailsNow()" 
                        style="padding: 8px 12px; background: #1976d2; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 12px;">
                        <i class="fas fa-sync-alt"></i>
                    </button>
                </div>
            `;
        }
        
        card.innerHTML = `
            <div class="business-header">
                ${businessTitleHtml}
                <span class="status-badge status-${statusClass}">${compactStatusText}</span>
            </div>
            <div class="business-details">
                ${business.city ? `<div class="detail"><i class="fas fa-map-marker-alt"></i><span>${this.escapeHtml(business.city)}</span></div>` : ''}
                ${contactRowHtml}
                ${compactNotesHtml}
                ${pendingActionsHtml}
            </div>
        `;
        
        return card;
    }
    
    getColumnForStatus(status) {
        const statusToAgent = {
            'found': 'lead_finder',
            'sdr_processing': 'sdr',
            'researched': 'sdr',
            'sdr_engaged': 'sdr',
            'contacted': 'sdr',
            'engaged': 'sdr',
            'pending': 'sdr',
            'not_interested': 'sdr',
            'no_response': 'sdr',
            'converting': 'lead_manager',
            'confirmed': 'lead_manager',
            'meeting_scheduled': 'calendar'
        };
        
        const agentType = statusToAgent[status];
        if (!agentType) return null;
        
        return document.querySelector(`[data-agent="${agentType}"]`);
    }
    
    getAgentForStatus(status) {
        const statusToAgent = {
            'found': 'lead_finder',
            'sdr_processing': 'sdr',
            'researched': 'sdr',
            'sdr_engaged': 'sdr',
            'contacted': 'sdr',
            'engaged': 'sdr',
            'pending': 'sdr',
            'not_interested': 'sdr',
            'no_response': 'sdr',
            'converting': 'lead_manager',
            'confirmed': 'lead_manager',
            'meeting_scheduled': 'calendar'
        };
        
        return statusToAgent[status] || 'unknown';
    }
    
    getStatusText(status) {
        const statusTexts = {
            'found': 'Found',
            'contacted': 'Contacted',
            'engaged': 'Engaged',
            'not_interested': 'Not Interested',
            'no_response': 'No Response',
            'converting': 'Converting',
            'meeting_scheduled': 'Meeting Scheduled',
            'pending': '⏳ Pending Confirmation',
            'confirmed': '✓ Confirmed',
            'sdr_engaged': 'SDR Engaged'
        };
        
        return statusTexts[status] || status;
    }
    
    updateStats() {
        const totalElement = document.getElementById('total-businesses');
        const engagedElement = document.getElementById('engaged-count');
        const convertingElement = document.getElementById('converting-count');
        const meetingsElement = document.getElementById('meetings-count');
        
        if (!totalElement) return;
        
        // Count cards in each column directly for accurate counts
        const leadFinderCards = document.querySelectorAll('#lead-finder-content .business-card').length;
        const sdrCards = document.querySelectorAll('#sdr-content .business-card').length;
        const leadManagerCards = document.querySelectorAll('#lead-manager-content .business-card').length;
        const calendarCards = document.querySelectorAll('#meeting-scheduled-content .business-card').length;
        
        // Total Leads = all businesses in the system
        this.animateCounter(totalElement, this.businesses.size);
        // Engaged = leads in SDR Agent column
        this.animateCounter(engagedElement, sdrCards);
        // Converting = leads in Lead Manager column
        this.animateCounter(convertingElement, leadManagerCards);
        // Meetings Scheduled = leads in Calendar column
        this.animateCounter(meetingsElement, calendarCards);
    }
    
    animateCounter(element, targetValue) {
        const currentValue = parseInt(element.textContent) || 0;
        if (currentValue === targetValue) return;
        
        const increment = targetValue > currentValue ? 1 : -1;
        const duration = 300;
        const steps = Math.abs(targetValue - currentValue);
        const stepDuration = duration / steps;
        
        let current = currentValue;
        const timer = setInterval(() => {
            current += increment;
            element.textContent = current;
            
            if (current === targetValue) {
                clearInterval(timer);
            }
        }, stepDuration);
    }
    
    updateAgentStatus(agentType, isActive) {
        const statusElement = document.getElementById(`${agentType.replace('_', '-')}-status`);
        if (!statusElement) return;
        
        const indicator = statusElement.querySelector('.status-indicator');
        if (!indicator) return;
        
        indicator.className = `status-indicator ${isActive ? 'active' : 'idle'}`;
    }
    
    updateAgentStatuses(isRunning) {
        const agents = ['lead-finder', 'sdr', 'lead-manager', 'calendar'];
        agents.forEach(agent => {
            this.updateAgentStatus(agent.replace('-', '_'), isRunning);
        });
    }
    
    addActivityLogEntry(agent, message, timestamp) {
        const logContent = document.getElementById('activity-log');
        if (!logContent) return;
        
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `
            <span class="log-time">${this.formatDateTime(timestamp)}</span>
            <span class="log-agent">${agent.replace('_', ' ')}</span>
            <span class="log-message">${this.escapeHtml(message)}</span>
        `;
        
        logContent.insertBefore(entry, logContent.firstChild);
        
        // Keep only last 50 entries
        const entries = logContent.querySelectorAll('.log-entry');
        if (entries.length > 50) {
            entries[entries.length - 1].remove();
        }
    }
    
    clearAllBusinessCards() {
        const contents = document.querySelectorAll('.column-content');
        contents.forEach(content => {
            content.innerHTML = '';
        });
    }
    
    showLoadingOverlay() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'flex';
        }
    }
    
    hideLoadingOverlay() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
    
    showErrorToast(message) {
        // Error toasts are muted - only log to console
        console.log('Error toast muted:', message);
    }
    
    updateConnectionStatus(isConnected) {
        // You can add visual feedback for connection status here
        console.log(`Connection status: ${isConnected ? 'Connected' : 'Disconnected'}`);
    }
    
    formatDateTime(dateTimeString) {
        try {
            const date = new Date(dateTimeString);
            return date.toLocaleString();
        } catch (error) {
            return dateTimeString;
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    initializeEventListeners() {
        // Any additional event listeners can be added here
    }
    
    handleSdrEngaged(data) {
        console.log('SDR engaged for business:', data.business_name, data);
        this.addActivityLogEntry('sdr', data.message, data.timestamp);
        this.showSuccessToast(`SDR Agent completed research for ${data.business_name}`);
        
        // Get the business from our map
        const business = this.businesses.get(data.business_id);
        if (business) {
            // Update business status
            business.status = 'sdr_engaged';
            business.sdr_processed = true;
            business.research = data.research;
            business.proposal = data.proposal;
            this.businesses.set(data.business_id, business);
            
            // Move the business card to SDR column
            this.moveBusinessToSdrColumn(business, data.research, data.proposal);
            
            // Update stats
            this.updateStats();
        } else {
            console.warn('Business not found in local state:', data.business_id);
        }
        
        // Update SDR agent status to show it's active
        this.updateAgentStatus('sdr', true);
        
        // Close the research dialog if it's open
        const researchDialog = document.getElementById('research-dialog-overlay');
        if (researchDialog && !researchDialog.classList.contains('hidden')) {
            // Don't close immediately - let user see the proposal
        }
        
        // Close the old SDR dialog if it's open
        const dialog = document.getElementById('sdr-dialog-overlay');
        if (dialog && !dialog.classList.contains('hidden')) {
            this.closeSdrDialog();
        }
    }
    
    handleLeadConfirmed(data) {
        console.log('Lead confirmed:', data);
        
        // Check if this was auto-confirmed via email
        const isAutoConfirmed = data.update && data.update.auto_confirmed;
        const confirmMessage = isAutoConfirmed 
            ? `📧 ${data.business.name} auto-confirmed via email reply!`
            : `${data.business.name} confirmed! Moving to Lead Manager...`;
        
        const logMessage = isAutoConfirmed 
            ? 'Lead auto-confirmed via email reply' 
            : 'Lead confirmed and moved to Lead Manager';
        
        this.addActivityLogEntry('lead_manager', logMessage, data.timestamp);
        this.showSuccessToast(confirmMessage);
        
        // Play a notification sound for auto-confirmations
        if (isAutoConfirmed) {
            this.playNotificationSound();
        }
        
        // Get the business and update it
        const business = this.businesses.get(data.business.id);
        if (business) {
            business.status = 'confirmed';
            this.businesses.set(data.business.id, business);
            
            // Find and remove the card from SDR column
            const existingCard = document.querySelector(`.business-card[data-business-id="${data.business.id}"]`);
            if (existingCard) {
                existingCard.remove();
            }
            
            // Add to Lead Manager column
            this.moveBusinessToLeadManagerColumn(business);
            
            // Update stats
            this.updateStats();
            
            // Update email tracking status
            this.updateEmailTrackingStatus();
        }
    }
    
    // Play a notification sound
    playNotificationSound() {
        try {
            // Create a simple beep sound using Web Audio API
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.3;
            
            oscillator.start();
            oscillator.stop(audioContext.currentTime + 0.2);
        } catch (e) {
            console.log('Could not play notification sound:', e);
        }
    }
    
    handleLeadRejected(data) {
        console.log('Lead rejected:', data);
        
        this.addActivityLogEntry('sdr', 'Lead declined via email reply', data.timestamp);
        this.showErrorToast(`${data.business.name} declined the proposal`);
        
        // Update the business status
        const business = this.businesses.get(data.business.id);
        if (business) {
            business.status = 'rejected';
            this.businesses.set(data.business.id, business);
            
            // Update the card in SDR column to show rejected status
            const card = document.querySelector(`.business-card[data-business-id="${data.business.id}"]`);
            if (card) {
                card.classList.add('rejected');
                const badge = card.querySelector('.status-badge');
                if (badge) {
                    badge.textContent = '✗ Declined';
                    badge.style.background = '#dc3545';
                }
            }
            
            // Update email tracking status
            this.updateEmailTrackingStatus();
        }
    }
    
    moveBusinessToLeadManagerColumn(business) {
        const leadManagerContent = document.getElementById('lead-manager-content');
        if (!leadManagerContent) {
            console.error('Lead Manager content column not found');
            return;
        }
        
        // Create Lead Manager business card
        const card = document.createElement('div');
        card.className = 'business-card compact confirmed';
        card.setAttribute('data-business-id', business.id);
        
        card.innerHTML = `
            <div class="business-header">
                <div class="business-title">
                    <h4>${this.escapeHtml(business.name)}</h4>
                </div>
                <span class="status-badge status-confirmed" style="background: #28a745;">✓ Confirmed</span>
            </div>
            <div class="business-details">
                <div class="detail">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>${this.escapeHtml(business.city || 'Unknown location')}</span>
                </div>
                ${business.phone ? `
                <div class="detail">
                    <i class="fas fa-phone"></i>
                    <span>${this.escapeHtml(business.phone)}</span>
                </div>` : ''}
            </div>
            <div class="lead-manager-actions" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e0e0e0;">
                <button class="btn-schedule-meeting" onclick="event.stopPropagation(); dashboardManagerInstance.showScheduleMeetingDialog('${business.id}', '${this.escapeHtml(business.name).replace(/'/g, "\\'")}')" 
                    style="width: 100%; padding: 10px 15px; background: linear-gradient(135deg, #4285f4 0%, #34a853 100%); 
                           color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;
                           display: flex; align-items: center; justify-content: center; gap: 8px; font-size: 14px;
                           box-shadow: 0 2px 8px rgba(66, 133, 244, 0.3); transition: all 0.3s ease;">
                    <i class="fas fa-calendar-plus"></i> Schedule a Meeting
                </button>
            </div>
        `;
        
        // Add to Lead Manager column with animation
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        leadManagerContent.insertBefore(card, leadManagerContent.firstChild);
        
        // Trigger animation
        requestAnimationFrame(() => {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        });
        
        // Update stats immediately after adding to Lead Manager column
        this.updateStats();
    }
    
    moveBusinessToSdrColumn(business, research, proposal) {
        // Remove from Lead Finder column if present
        const existingCard = document.querySelector(`.business-card[data-business-id="${business.id}"]`);
        
        // Get the SDR content area
        const sdrContent = document.getElementById('sdr-content');
        if (!sdrContent) {
            console.error('SDR content column not found');
            return;
        }
        
        // Create SDR business card
        const card = document.createElement('div');
        card.className = 'business-card sdr-card compact';
        card.setAttribute('data-business-id', business.id);
        
        // Build the card HTML
        const industry = research?.industry || 'Business';
        const priority = research?.recommendation?.priority || 'medium';
        
        card.innerHTML = `
            <div class="business-header">
                <div class="business-title">
                    <h4>${this.escapeHtml(business.name)}</h4>
                </div>
                <span class="status-badge status-researched">Researched</span>
            </div>
            <div class="business-details">
                <div class="detail">
                    <i class="fas fa-industry"></i>
                    <span>${this.escapeHtml(industry)}</span>
                </div>
                <div class="detail">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>${this.escapeHtml(business.city || business.address || 'Unknown location')}</span>
                </div>
                ${business.rating ? `
                <div class="detail">
                    <i class="fas fa-star"></i>
                    <span>${business.rating}/5 (${business.review_count || 0} reviews)</span>
                </div>
                ` : ''}
                <div class="detail priority-${priority}">
                    <i class="fas fa-flag"></i>
                    <span>Priority: ${priority.charAt(0).toUpperCase() + priority.slice(1)}</span>
                </div>
            </div>
            <div class="sdr-actions">
                <button class="btn-small btn-view" onclick="event.stopPropagation(); dashboardManagerInstance.viewSdrResults('${business.id}')">
                    <i class="fas fa-eye"></i> View Research
                </button>
                <button class="btn-small btn-success" onclick="event.stopPropagation(); dashboardManagerInstance.showEmailDraftDialog(dashboardManagerInstance.businesses.get('${business.id}'))">
                    <i class="fas fa-envelope"></i> Send Email
                </button>
                <button class="btn-small btn-website" onclick="event.stopPropagation(); dashboardManagerInstance.showWebsitePromptDialog('${business.id}')">
                    <i class="fas fa-magic"></i> Create Website
                </button>
            </div>
        `;
        
        // Add click handler for the card - show email draft on click
        card.addEventListener('click', (e) => {
            if (!e.target.closest('button')) {
                this.showEmailDraftDialog(business);
            }
        });
        card.style.cursor = 'pointer';
        
        // Add to SDR column
        sdrContent.insertBefore(card, sdrContent.firstChild);
        
        // Update stats immediately after adding to SDR column
        this.updateStats();
        
        // If original card exists in lead finder, mark it as processed
        if (existingCard) {
            existingCard.classList.add('sdr-sent');
            const badge = existingCard.querySelector('.status-badge');
            if (badge) {
                badge.textContent = 'SDR Processing';
                badge.className = 'status-badge status-engaged';
            }
        }
    }
    
    viewSdrResults(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) {
            console.error('Business not found:', businessId);
            return;
        }
        
        // If we have stored research/proposal, show it in the research dialog
        if (business.research || business.proposal) {
            this.currentResearchBusiness = business;
            
            // Show research dialog with results
            const overlay = document.getElementById('research-dialog-overlay');
            if (overlay) {
                overlay.classList.remove('hidden');
                
                // Hide loading/error, show results
                const loading = document.getElementById('research-loading');
                const resultsDiv = document.getElementById('research-results');
                const error = document.getElementById('research-error');
                
                if (loading) loading.classList.add('hidden');
                if (error) error.classList.add('hidden');
                if (resultsDiv) {
                    resultsDiv.classList.remove('hidden');
                    
                    // Display the research
                    if (business.research) {
                        this.displayResearchResults({
                            success: true,
                            research: business.research,
                            business_info: business
                        });
                    }
                    
                    // Display proposal if available
                    if (business.proposal) {
                        this.displayProposal(business.proposal, business.research);
                    }
                }
            }
        } else {
            // No stored results, trigger new research
            this.showResearchDialog(business);
        }
    }
    
    sendToLeadManager(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) {
            console.error('Business not found:', businessId);
            return;
        }
        
        // Update status
        business.status = 'qualified';
        this.businesses.set(businessId, business);
        
        // Move to Lead Manager column
        this.moveBusinessToLeadManager(business);
        
        this.showSuccessToast(`${business.name} sent to Lead Manager`);
        this.addActivityLogEntry('lead_manager', `Received qualified lead: ${business.name}`, new Date().toISOString());
        this.updateAgentStatus('lead_manager', true);
    }
    
    moveBusinessToLeadManager(business) {
        // Remove from SDR column
        const sdrCard = document.querySelector(`#sdr-content .business-card[data-business-id="${business.id}"]`);
        if (sdrCard) {
            sdrCard.remove();
        }
        
        // Get Lead Manager content area
        const leadManagerContent = document.getElementById('lead-manager-content');
        if (!leadManagerContent) {
            console.error('Lead Manager content column not found');
            return;
        }
        
        // Create Lead Manager card
        const card = document.createElement('div');
        card.className = 'business-card compact lead-qualified';
        card.setAttribute('data-business-id', business.id);
        
        const research = business.research || {};
        const priority = research.recommendation?.priority || 'medium';
        
        card.innerHTML = `
            <div class="business-header">
                <div class="business-title">
                    <h4>${this.escapeHtml(business.name)}</h4>
                </div>
                <span class="status-badge status-qualified">Qualified</span>
            </div>
            <div class="business-details">
                <div class="detail">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>${this.escapeHtml(business.city || business.address || 'Unknown')}</span>
                </div>
                <div class="detail priority-${priority}">
                    <i class="fas fa-flag"></i>
                    <span>Priority: ${priority.charAt(0).toUpperCase() + priority.slice(1)}</span>
                </div>
            </div>
            <div class="lead-actions">
                <button class="btn-small btn-view" onclick="dashboardManagerInstance.viewSdrResults('${business.id}')">
                    <i class="fas fa-file-alt"></i> View Proposal
                </button>
                <button class="btn-small btn-success" onclick="dashboardManagerInstance.scheduleCall('${business.id}')">
                    <i class="fas fa-phone"></i> Schedule Call
                </button>
            </div>
        `;
        
        // Add to Lead Manager column
        leadManagerContent.insertBefore(card, leadManagerContent.firstChild);
    }
    
    scheduleCall(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) return;
        
        this.showSuccessToast(`Call scheduled for ${business.name}`);
        this.addActivityLogEntry('calendar', `Call scheduled with ${business.name}`, new Date().toISOString());
    }
    
    handleHumanInputRequest(data) {
        console.log('Received human input request:', data);
        console.log('About to show human input dialog...');
        this.addActivityLogEntry('sdr', 'Requesting human input for website creation', data.timestamp);
        
        // Show the human input modal
        showHumanInputDialog(data);
        console.log('Human input dialog show function called');
    }
    
    handleHumanInputResponseSubmitted(data) {
        console.log('Human input response submitted:', data);
        this.addActivityLogEntry('sdr', `Website URL submitted: ${data.response}`, data.timestamp);
        // Close the human input dialog if it's still open
        closeHumanInputDialog();
    }
    
    /**
     * Handle incoming calendar (meeting) notifications (meeting request stage).
     * @param {Object} data - Payload with meeting request details
     */
    handleCalendarNotification(data) {
        console.log('Received calendar notification:', data);
        this.addActivityLogEntry('calendar', data.message, data.timestamp);
        const container = document.getElementById('meeting-scheduled-content');
        if (!container) {
            console.error('Calendar column-content not found (id="meeting-scheduled-content")');
            return;
        }
        const req = data.data || {};
        const card = document.createElement('div');
        // Use the same meeting-card style as other business cards
        card.className = 'business-card compact meeting-card';
        card.setAttribute('data-business-id', `${data.business_id}-meeting`);
        const title = req.title || '';
        const desc = req.description || '';
        const start = req.start_datetime || '';
        const end = req.end_datetime || '';
        const attendees = Array.isArray(req.attendees) ? req.attendees : [];
        card.innerHTML = `
            <div class="business-header">
                <div class="business-title">
                    <i class="fas fa-handshake meeting-icon"></i>
                    <h4>${this.escapeHtml(title)}</h4>
                </div>
                <span class="status-badge status-meeting-scheduled">Meeting</span>
            </div>
            <div class="business-details">
                ${desc ? `<div class="detail"><i class="fas fa-info-circle"></i><span>${this.escapeHtml(desc)}</span></div>` : ''}
                <div class="detail"><i class="fas fa-calendar-alt"></i><span>${this.escapeHtml(this.formatDateTime(start))} - ${this.escapeHtml(this.formatDateTime(end))}</span></div>
                ${attendees.length ? `<div class="detail"><i class="fas fa-users"></i><span>${attendees.map(a => this.escapeHtml(a)).join(', ')}</span></div>` : ''}
            </div>
        `;
        container.appendChild(card);
    }
    
    /**
     * Handle meeting scheduled event from WebSocket
     * This is triggered when a meeting is created via the backend API
     */
    handleMeetingScheduled(data) {
        console.log('Meeting scheduled event received:', data);
        
        const businessId = data.business_id;
        const businessName = data.business_name;
        const meeting = data.meeting || {};
        
        // Get business from local state or create minimal one
        let business = this.businesses.get(businessId);
        if (business) {
            business.status = 'meeting_scheduled';
            this.businesses.set(businessId, business);
        } else {
            business = { id: businessId, name: businessName, status: 'meeting_scheduled' };
        }
        
        // Create meeting info from the event data
        const meetingInfo = {
            businessId: businessId,
            businessName: businessName,
            title: meeting.title || `Meeting with ${businessName}`,
            date: meeting.date || new Date().toISOString().split('T')[0],
            time: meeting.time || '10:00',
            duration: meeting.duration || 30,
            attendee: meeting.attendee || '',
            description: meeting.description || '',
            meet_link: meeting.meet_link || '',
            calendar_link: meeting.calendar_link || '',
            meeting_id: meeting.meeting_id || '',
            createdAt: data.timestamp || new Date().toISOString(),
            status: 'scheduled'
        };
        
        // Store meeting info
        if (!this.scheduledMeetings) {
            this.scheduledMeetings = new Map();
        }
        this.scheduledMeetings.set(businessId, meetingInfo);
        
        // Move to calendar column
        this.moveBusinessToCalendarColumn(business, meetingInfo);
        
        // Show success toast
        if (meetingInfo.meet_link) {
            this.showSuccessToast(`Meeting scheduled with ${businessName}! Meet link ready.`);
        } else {
            this.showSuccessToast(`Meeting scheduled with ${businessName}!`);
        }
        
        // Add activity log
        this.addActivityLogEntry('calendar', `Meeting scheduled: ${meetingInfo.title}`, data.timestamp);
    }
    
    // ===== Research Dialog Methods =====
    
    async showResearchDialog(business) {
        console.log('Showing research dialog for business:', business.name);
        
        // Store current business for later use
        this.currentResearchBusiness = business;
        
        // Get dialog elements
        const dialog = document.getElementById('research-dialog-overlay');
        const loadingDiv = document.getElementById('research-loading');
        const resultsDiv = document.getElementById('research-results');
        const errorDiv = document.getElementById('research-error');
        const sdrBtn = document.getElementById('send-to-sdr-btn');
        
        if (!dialog) {
            console.error('Research dialog not found!');
            return;
        }
        
        // Reset state
        loadingDiv.classList.remove('hidden');
        resultsDiv.classList.add('hidden');
        errorDiv.classList.add('hidden');
        if (sdrBtn) {
            sdrBtn.disabled = true;
            sdrBtn.setAttribute('data-business-id', business.id);
        }
        
        // Show dialog
        dialog.classList.remove('hidden');
        
        // Fetch research data
        try {
            const response = await fetch(`/research_business/${business.id}`);
            const data = await response.json();
            
            if (data.success && data.research) {
                this.displayResearchResults(data);
                loadingDiv.classList.add('hidden');
                resultsDiv.classList.remove('hidden');
                if (sdrBtn) {
                    sdrBtn.disabled = false;
                }
            } else {
                this.showResearchError(data.error || 'Failed to research business');
            }
        } catch (error) {
            console.error('Error fetching research:', error);
            this.showResearchError('Network error: ' + error.message);
        }
    }
    
    displayResearchResults(data) {
        const research = data.research;
        const businessInfo = data.business_info || {};
        
        // Ensure loading/error are hidden and results are visible
        const loadingDiv = document.getElementById('research-loading');
        const resultsDiv = document.getElementById('research-results');
        const errorDiv = document.getElementById('research-error');
        
        if (loadingDiv) loadingDiv.classList.add('hidden');
        if (errorDiv) errorDiv.classList.add('hidden');
        if (resultsDiv) resultsDiv.classList.remove('hidden');
        
        // Populate business info header with enhanced layout
        const infoHeader = document.getElementById('research-business-info');
        infoHeader.innerHTML = `
            <h3><i class="fas fa-store"></i> ${this.escapeHtml(data.business_name)}</h3>
            <div class="meta">
                ${businessInfo.city ? `<span class="meta-item"><i class="fas fa-map-marker-alt"></i> ${this.escapeHtml(businessInfo.city)}</span>` : ''}
                ${businessInfo.phone ? `<span class="meta-item"><i class="fas fa-phone"></i> ${this.escapeHtml(businessInfo.phone)}</span>` : ''}
                ${businessInfo.rating ? `<span class="meta-item rating"><i class="fas fa-star"></i> ${businessInfo.rating}/5 (${businessInfo.review_count || 0} reviews)</span>` : ''}
            </div>
        `;
        
        // Overview
        document.getElementById('research-overview').textContent = research.overview || 'No overview available';
        document.getElementById('research-industry').textContent = research.industry || 'Unknown Industry';
        
        // Target customers
        document.getElementById('research-target-customers').textContent = research.target_customers || 'Not specified';
        
        // Services
        const servicesList = document.getElementById('research-services');
        servicesList.innerHTML = '';
        if (research.services && Array.isArray(research.services)) {
            research.services.forEach(service => {
                const li = document.createElement('li');
                li.textContent = service;
                servicesList.appendChild(li);
            });
        } else {
            servicesList.innerHTML = '<li>No services information available</li>';
        }
        
        // Online presence
        const presenceDiv = document.getElementById('research-online-presence');
        if (research.online_presence_analysis) {
            const presence = research.online_presence_analysis;
            presenceDiv.innerHTML = `
                <div class="presence-item">
                    <div class="label">Current Status</div>
                    <div class="value">${this.escapeHtml(presence.current_status || 'No website')}</div>
                </div>
                <div class="presence-item">
                    <div class="label">Social Media</div>
                    <div class="value">${this.escapeHtml(presence.social_media_likely || 'Unknown')}</div>
                </div>
                <div class="presence-item">
                    <div class="label">Visibility</div>
                    <div class="value ${(presence.visibility_score || '').toLowerCase()}">${this.escapeHtml(presence.visibility_score || 'Unknown')}</div>
                </div>
            `;
        } else {
            presenceDiv.innerHTML = '<p>No online presence analysis available</p>';
        }
        
        // Pain points
        const painPointsList = document.getElementById('research-pain-points');
        painPointsList.innerHTML = '';
        if (research.pain_points && Array.isArray(research.pain_points)) {
            research.pain_points.forEach(point => {
                const li = document.createElement('li');
                li.textContent = point;
                painPointsList.appendChild(li);
            });
        }
        
        // Benefits
        const benefitsList = document.getElementById('research-benefits');
        benefitsList.innerHTML = '';
        if (research.website_benefits && Array.isArray(research.website_benefits)) {
            research.website_benefits.forEach(benefit => {
                const li = document.createElement('li');
                li.textContent = benefit;
                benefitsList.appendChild(li);
            });
        }
        
        // Recommendation
        const recommendationDiv = document.getElementById('research-recommendation');
        if (research.recommendation) {
            const rec = research.recommendation;
            const featuresHtml = (rec.suggested_features || []).map(f => 
                `<span class="feature-tag">${this.escapeHtml(f)}</span>`
            ).join('');
            
            recommendationDiv.innerHTML = `
                <span class="priority ${(rec.priority || '').toLowerCase()}">${this.escapeHtml(rec.priority || 'Medium')} Priority</span>
                <p class="reason">${this.escapeHtml(rec.reason || 'Website recommended')}</p>
                ${featuresHtml ? `<div class="features">${featuresHtml}</div>` : ''}
            `;
        } else {
            recommendationDiv.innerHTML = '<p>No specific recommendation available</p>';
        }
        
        // Conversation starters
        const conversationList = document.getElementById('research-conversation-starters');
        conversationList.innerHTML = '';
        if (research.conversation_starters && Array.isArray(research.conversation_starters)) {
            research.conversation_starters.forEach(starter => {
                const li = document.createElement('li');
                li.textContent = `"${starter}"`;
                conversationList.appendChild(li);
            });
        }
    }
    
    showResearchError(message) {
        const loadingDiv = document.getElementById('research-loading');
        const errorDiv = document.getElementById('research-error');
        const errorMessage = document.getElementById('research-error-message');
        
        loadingDiv.classList.add('hidden');
        errorDiv.classList.remove('hidden');
        errorMessage.textContent = message;
    }
    
    closeResearchDialog() {
        const dialog = document.getElementById('research-dialog-overlay');
        if (dialog) {
            dialog.classList.add('hidden');
        }
        this.currentResearchBusiness = null;
    }
    
    proceedToSdr() {
        // Close research dialog
        this.closeResearchDialog();
        
        // Open SDR dialog with the same business
        if (this.currentResearchBusiness) {
            this.showSdrDialog(this.currentResearchBusiness);
        }
    }
    
    async sendToSdrDirect() {
        // Send directly to SDR agent without phone number step
        if (!this.currentResearchBusiness) {
            console.error('No business selected for SDR');
            return;
        }
        
        const business = this.currentResearchBusiness;
        const button = document.getElementById('send-to-sdr-btn');
        
        // Disable button and show loading
        if (button) {
            button.disabled = true;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending to SDR...';
        }
        
        try {
            const formData = new FormData();
            formData.append('business_id', business.id);
            // Phone number is optional - SDR will use business phone if available
            
            const response = await fetch('/send_to_sdr', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                let errorMessage = 'Failed to send to SDR agent';
                try {
                    const errorResult = JSON.parse(errorText);
                    errorMessage = errorResult.error || errorMessage;
                } catch (e) {
                    errorMessage = `Server error: ${response.status}`;
                }
                
                console.error('Error sending to SDR:', errorMessage);
                this.showErrorToast(errorMessage);
                
                // Reset button
                if (button) {
                    button.disabled = false;
                    button.innerHTML = '<i class="fas fa-robot"></i> Send to SDR Agent';
                }
                return;
            }
            
            const result = await response.json();
            
            if (result.success) {
                console.log('Successfully processed by SDR:', result.message);
                
                // Update stats immediately when sent to SDR
                this.updateStats();
                
                // Show the proposal in the research dialog if available
                if (result.proposal) {
                    this.displayProposal(result.proposal, result.research);
                    this.showSuccessToast(`SDR Agent completed analysis for ${business.name}`);
                } else {
                    this.showSuccessToast(`${business.name} sent to SDR Agent for research and prospectus generation`);
                    this.closeResearchDialog();
                }
                
                // Reset button with success state
                if (button) {
                    button.disabled = false;
                    button.innerHTML = '<i class="fas fa-check"></i> SDR Complete';
                    button.classList.add('btn-success');
                }
            } else {
                console.error('Failed to send to SDR:', result.error);
                this.showErrorToast(result.error || 'Failed to send to SDR agent');
                
                // Reset button
                if (button) {
                    button.disabled = false;
                    button.innerHTML = '<i class="fas fa-robot"></i> Send to SDR Agent';
                }
            }
        } catch (error) {
            console.error('Network error sending to SDR:', error);
            this.showErrorToast('Network error: ' + error.message);
            
            // Reset button
            if (button) {
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-robot"></i> Send to SDR Agent';
            }
        }
    }
    
    displayProposal(proposal, research) {
        // Find or create proposal section in the research dialog
        const researchContent = document.getElementById('research-content');
        if (!researchContent) return;
        
        // Create proposal section
        const proposalSection = document.createElement('div');
        proposalSection.className = 'proposal-section';
        proposalSection.innerHTML = `
            <div class="proposal-header">
                <i class="fas fa-file-signature"></i>
                <h3>Generated Sales Proposal</h3>
            </div>
            <div class="proposal-content">
                <p>${proposal.replace(/\n/g, '</p><p>')}</p>
            </div>
            <div class="email-input-section" style="margin: 15px 0; padding: 15px; background: #f5f5f5; border-radius: 8px;">
                <label for="recipient-email" style="display: block; margin-bottom: 8px; font-weight: 600;">
                    <i class="fas fa-envelope"></i> Recipient Email Address:
                </label>
                <input type="email" id="recipient-email" placeholder="Enter business email address" 
                    style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; margin-bottom: 10px;">
            </div>
            <div class="proposal-actions">
                <button class="btn-secondary" onclick="dashboardManagerInstance.copyProposal()">
                    <i class="fas fa-copy"></i> Copy Proposal
                </button>
                <button class="btn-primary" onclick="dashboardManagerInstance.downloadProposal()">
                    <i class="fas fa-download"></i> Download as PDF
                </button>
                <button class="btn-primary" onclick="dashboardManagerInstance.sendEmailProposal()" style="background: #28a745; margin-left: 10px;">
                    <i class="fas fa-paper-plane"></i> Send Email
                </button>
            </div>
        `;
        
        // Store proposal for later use
        this.currentProposal = proposal;
        
        // Insert at the top of research content
        researchContent.insertBefore(proposalSection, researchContent.firstChild);
        
        // Scroll to top to show proposal
        researchContent.scrollTop = 0;
    }
    
    copyProposal() {
        if (this.currentProposal) {
            navigator.clipboard.writeText(this.currentProposal).then(() => {
                this.showSuccessToast('Proposal copied to clipboard!');
            }).catch(err => {
                console.error('Failed to copy:', err);
                this.showErrorToast('Failed to copy proposal');
            });
        }
    }
    
    downloadProposal() {
        if (!this.currentProposal || !this.currentResearchBusiness) return;
        
        // Create a simple text file for now
        const businessName = this.currentResearchBusiness.name.replace(/[^a-z0-9]/gi, '_');
        const content = `Sales Proposal for ${this.currentResearchBusiness.name}\n${'='.repeat(50)}\n\n${this.currentProposal}\n\n---\nGenerated by SalesShortcut SDR Agent`;
        
        const blob = new Blob([content], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `proposal_${businessName}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showSuccessToast('Proposal downloaded!');
    }
    
    async sendEmailProposal() {
        if (!this.currentProposal || !this.currentResearchBusiness) {
            this.showErrorToast('No proposal or business data available');
            return;
        }
        
        const emailInput = document.getElementById('recipient-email');
        const recipientEmail = emailInput ? emailInput.value.trim() : '';
        
        if (!recipientEmail) {
            this.showErrorToast('Please enter a recipient email address');
            return;
        }
        
        // Validate email format
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(recipientEmail)) {
            this.showErrorToast('Please enter a valid email address');
            return;
        }
        
        try {
            // Prepare email data
            const subject = `Proposal for ${this.currentResearchBusiness.name} - Website Development Services`;
            const body = `Dear ${this.currentResearchBusiness.name} Team,\n\n${this.currentProposal}\n\nBest regards,\nSales Team`;
            
            const formData = new FormData();
            formData.append('business_id', this.currentResearchBusiness.id);
            formData.append('recipient_email', recipientEmail);
            formData.append('subject', subject);
            formData.append('body', body);
            
            this.showSuccessToast('Sending email...');
            
            const response = await fetch('/send_email', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccessToast(`Email sent successfully to ${recipientEmail}!`);
                emailInput.value = ''; // Clear the input
            } else {
                this.showErrorToast(result.error || 'Failed to send email');
            }
        } catch (error) {
            console.error('Error sending email:', error);
            this.showErrorToast('Failed to send email. Please try again.');
        }
    }
    
    showSuccessToast(message) {
        // Create a success toast notification
        const toast = document.createElement('div');
        toast.className = 'toast toast-success';
        toast.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => toast.classList.add('show'), 100);
        
        // Remove after 4 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }
    
    // ===== Email Draft Dialog Methods =====
    
    showEmailDraftDialog(business) {
        console.log('Showing email draft for business:', business.name);
        
        // Store current business for email sending
        this.currentEmailBusiness = business;
        
        // Generate personalized email content
        const emailDraft = this.generatePersonalizedEmail(business);
        
        // Create and show email draft modal
        const modalHtml = `
            <div class="modal-overlay" id="email-draft-overlay" onclick="dashboardManagerInstance.closeEmailDraft(event)">
                <div class="modal-dialog" style="max-width: 700px;" onclick="event.stopPropagation()">
                    <div class="modal-header">
                        <h3><i class="fas fa-envelope-open-text"></i> Email Draft - ${this.escapeHtml(business.name)}</h3>
                        <button class="modal-close" onclick="dashboardManagerInstance.closeEmailDraft()">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-content" style="max-height: 70vh; overflow-y: auto;">
                        <div class="business-info" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                            <h4 style="margin-top: 0; color: #2c3e50;">Business Information</h4>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                <div><strong>Name:</strong> ${this.escapeHtml(business.name)}</div>
                                <div><strong>Location:</strong> ${this.escapeHtml(business.city || 'N/A')}</div>
                                <div><strong>Phone:</strong> ${this.escapeHtml(business.phone || 'N/A')}</div>
                                <div><strong>Rating:</strong> ${business.rating ? '⭐ ' + business.rating : 'N/A'}</div>
                            </div>
                        </div>
                        
                        <div class="email-draft-section">
                            <label style="display: block; margin-bottom: 8px; font-weight: 600;">
                                <i class="fas fa-paper-plane"></i> Email will be sent to: kundarvinayak2004@gmail.com
                            </label>
                            
                            <label for="email-draft-content" style="display: block; margin: 15px 0 8px; font-weight: 600;">
                                <i class="fas fa-edit"></i> Edit Email Content:
                            </label>
                            <textarea id="email-draft-content" 
                                style="width: 100%; min-height: 300px; padding: 15px; 
                                       border: 1px solid #ddd; border-radius: 8px; 
                                       font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;"
                            >${emailDraft}</textarea>
                            
                            <div style="background: #fff3cd; padding: 12px; border-radius: 5px; margin-top: 15px; border-left: 4px solid #ffc107;">
                                <strong>📧 Note:</strong> This email will include a confirmation button. 
                                When clicked, it will automatically move this lead from SDR to Lead Manager.
                            </div>
                        </div>
                    </div>
                    <div class="modal-actions" style="border-top: 1px solid #ddd; padding-top: 15px; margin-top: 15px;">
                        <button class="btn-secondary" onclick="dashboardManagerInstance.closeEmailDraft()">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                        <button class="btn-primary" onclick="dashboardManagerInstance.sendConfirmationEmail()" 
                            style="background: #28a745;">
                            <i class="fas fa-paper-plane"></i> Send Email
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Remove any existing modal
        const existingModal = document.getElementById('email-draft-overlay');
        if (existingModal) existingModal.remove();
        
        // Add to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    generatePersonalizedEmail(business) {
        const businessName = business.name || 'Valued Business';
        const location = business.city || 'your area';
        const rating = business.rating ? `with a stellar ${business.rating}⭐ rating` : '';
        
        return `Dear ${businessName} Team,

I hope this message finds you well!

I came across your business ${rating} in ${location}, and I wanted to reach out with an exciting opportunity that could significantly enhance your online presence.

In today's digital age, having a professional website is crucial for:
✓ Reaching more customers
✓ Building credibility and trust
✓ Showcasing your services 24/7
✓ Standing out from competitors

We specialize in creating stunning, user-friendly websites tailored specifically for businesses like yours. Our team would love to:

• Provide a FREE consultation to understand your needs
• Create a custom website design that reflects your brand
• Ensure mobile-friendly and SEO-optimized results
• Offer competitive pricing and ongoing support

I'd be delighted to schedule a brief call to discuss how we can help ${businessName} thrive online.

If you're interested, simply click the confirmation button below, and we'll be in touch shortly!

Looking forward to partnering with you.

Best regards,
Sales Team
SalesShortcut

---
Business Details:
Name: ${businessName}
Location: ${location}
Phone: ${business.phone || 'N/A'}`;
    }
    
    async sendConfirmationEmail() {
        const emailContent = document.getElementById('email-draft-content');
        if (!emailContent || !this.currentEmailBusiness) {
            this.showErrorToast('Email content not found');
            return;
        }
        
        const body = emailContent.value.trim();
        if (!body) {
            this.showErrorToast('Email content cannot be empty');
            return;
        }
        
        try {
            this.showSuccessToast('Sending email...');
            
            const formData = new FormData();
            formData.append('business_id', this.currentEmailBusiness.id);
            formData.append('email_body', body);
            
            const response = await fetch('/send_confirmation_email', {
                method: 'POST',
                body: formData
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccessToast('Email sent! Awaiting confirmation...');
                this.closeEmailDraft();
                
                // The business status will be updated via WebSocket
            } else {
                this.showErrorToast(result.error || 'Failed to send email');
            }
        } catch (error) {
            console.error('Error sending confirmation email:', error);
            this.showErrorToast('Failed to send email. Please try again.');
        }
    }
    
    closeEmailDraft(event) {
        if (event && event.target.id !== 'email-draft-overlay') return;
        
        const modal = document.getElementById('email-draft-overlay');
        if (modal) modal.remove();
        
        this.currentEmailBusiness = null;
    }
    
    // Manual confirmation - user clicks "Confirm Lead" after receiving positive response
    async confirmLeadManually(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) {
            this.showErrorToast('Business not found');
            return;
        }
        
        // Show confirmation dialog
        const confirmed = confirm(`Are you sure you want to confirm "${business.name}" as a qualified lead?\n\nThis will move the lead to the Lead Manager column.`);
        if (!confirmed) return;
        
        try {
            // Call the API to confirm the lead
            const response = await fetch(`/confirm_lead/${businessId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccessToast(`Lead "${business.name}" confirmed and moved to Lead Manager!`);
                
                // Update local business status
                business.status = 'confirmed';
                this.businesses.set(businessId, business);
                
                // Move to Lead Manager column
                this.moveBusinessToLeadManagerColumn(business);
                
                // Remove from SDR column
                const sdrCard = document.querySelector(`#sdr-column .business-card[data-business-id="${businessId}"]`);
                if (sdrCard) sdrCard.remove();
                
                // Update card counts
                this.updateColumnCounts();
            } else {
                this.showErrorToast(result.error || 'Failed to confirm lead');
            }
        } catch (error) {
            console.error('Error confirming lead:', error);
            this.showErrorToast('Failed to confirm lead. Please try again.');
        }
    }
    
    // Manual confirmation - quick confirm from pending card
    async manualConfirmLead(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) {
            this.showErrorToast('Business not found');
            return;
        }
        
        try {
            // Call the API to confirm the lead
            const response = await fetch(`/confirm_lead/${businessId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const result = await response.json();
            
            if (result.success) {
                this.showSuccessToast(`Lead "${business.name}" confirmed!`);
                
                // Update local business status
                business.status = 'confirmed';
                this.businesses.set(businessId, business);
                
                // Remove from SDR column
                const sdrCard = document.querySelector(`.business-card[data-business-id="${businessId}"]`);
                if (sdrCard) sdrCard.remove();
                
                // Move to Lead Manager column
                this.moveBusinessToLeadManagerColumn(business);
                
                // Update stats
                this.updateStats();
            } else {
                this.showErrorToast(result.error || 'Failed to confirm lead');
            }
        } catch (error) {
            console.error('Error confirming lead:', error);
            this.showErrorToast('Failed to confirm lead. Please try again.');
        }
    }
    
    // Check emails for replies (force immediate check)
    async checkEmailsNow() {
        console.log('Forcing email check...');
        const statusEl = document.getElementById('email-tracking-status');
        
        try {
            if (statusEl) {
                statusEl.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking inbox...';
            }
            
            const response = await fetch('/email_tracking/check_now', { method: 'POST' });
            const result = await response.json();
            
            if (result.success) {
                this.showSuccessToast('Checking inbox for replies...');
                
                // Update status after a delay
                setTimeout(async () => {
                    await this.updateEmailTrackingStatus();
                }, 3000);
            } else {
                this.showErrorToast(result.error || 'Failed to check emails');
                if (statusEl) {
                    statusEl.textContent = 'Email tracking error';
                }
            }
        } catch (error) {
            console.error('Error checking emails:', error);
            this.showErrorToast('Failed to check emails');
            if (statusEl) {
                statusEl.textContent = 'Email tracking unavailable';
            }
        }
    }
    
    // Update email tracking status display
    async updateEmailTrackingStatus() {
        const statusEl = document.getElementById('email-tracking-status');
        if (!statusEl) return;
        
        try {
            const response = await fetch('/email_tracking/status');
            const data = await response.json();
            
            if (data.enabled && data.is_running) {
                const pendingCount = data.pending_leads_count || 0;
                if (pendingCount > 0) {
                    statusEl.innerHTML = `<i class="fas fa-clock"></i> Tracking ${pendingCount} pending lead${pendingCount > 1 ? 's' : ''}`;
                } else {
                    statusEl.innerHTML = '<i class="fas fa-check-circle"></i> Email tracking active';
                }
            } else if (data.enabled) {
                statusEl.textContent = 'Email tracking paused';
            } else {
                statusEl.textContent = 'Email tracking unavailable';
            }
        } catch (error) {
            console.error('Error getting email tracking status:', error);
        }
    }

    // ===== End Email Draft Dialog Methods =====
    
    // ===== Website Creation Prompt Methods =====
    
    showWebsitePromptDialog(businessId) {
        const business = this.businesses.get(businessId);
        if (!business) {
            this.showErrorToast('Business not found');
            return;
        }
        
        console.log('Showing website prompt for business:', business.name);
        
        // Generate the website creation prompt
        const websitePrompt = this.generateWebsitePrompt(business);
        
        // Store for later use
        this.currentWebsiteBusiness = business;
        
        // Create modal HTML
        const modalHtml = `
            <div class="modal-overlay" id="website-prompt-overlay" onclick="dashboardManagerInstance.closeWebsitePrompt(event)">
                <div class="modal-dialog" style="max-width: 800px;" onclick="event.stopPropagation()">
                    <div class="modal-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 12px 12px 0 0;">
                        <h3 style="margin: 0; display: flex; align-items: center; gap: 10px;">
                            <i class="fas fa-magic"></i> Website Creation Prompt - ${this.escapeHtml(business.name)}
                        </h3>
                        <button class="modal-close" onclick="dashboardManagerInstance.closeWebsitePrompt()" style="color: white; background: rgba(255,255,255,0.2);">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-content" style="max-height: 60vh; overflow-y: auto; padding: 20px;">
                        <div class="business-summary" style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                            <h4 style="margin-top: 0; color: #2c3e50; display: flex; align-items: center; gap: 8px;">
                                <i class="fas fa-store"></i> Business Information
                            </h4>
                            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; font-size: 14px;">
                                <div><strong>Name:</strong> ${this.escapeHtml(business.name)}</div>
                                <div><strong>Location:</strong> ${this.escapeHtml(business.city || 'N/A')}</div>
                                <div><strong>Phone:</strong> ${this.escapeHtml(business.phone || 'N/A')}</div>
                                <div><strong>Rating:</strong> ${business.rating ? '⭐ ' + business.rating : 'N/A'}</div>
                            </div>
                        </div>
                        
                        <div class="prompt-section">
                            <label style="display: block; margin-bottom: 10px; font-weight: 600; color: #2c3e50; font-size: 16px;">
                                <i class="fas fa-edit"></i> Edit Your Website Creation Prompt:
                            </label>
                            <p style="color: #666; font-size: 13px; margin-bottom: 10px;">
                                This prompt is customized for ${this.escapeHtml(business.name)}. 
                                Feel free to edit it to add more details or customize the website requirements.
                            </p>
                            <textarea id="website-prompt-content" 
                                style="width: 100%; min-height: 350px; padding: 15px; 
                                       border: 2px solid #667eea; border-radius: 8px; 
                                       font-family: 'Monaco', 'Consolas', monospace; font-size: 13px; line-height: 1.6;
                                       background: #fafafa; resize: vertical;"
                            >${websitePrompt}</textarea>
                        </div>
                        
                        <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 15px; border-radius: 8px; margin-top: 15px; border-left: 4px solid #2196f3;">
                            <div style="display: flex; align-items: flex-start; gap: 10px;">
                                <i class="fas fa-info-circle" style="color: #1976d2; font-size: 20px; margin-top: 2px;"></i>
                                <div>
                                    <strong style="color: #1565c0;">How it works:</strong>
                                    <p style="margin: 5px 0 0 0; color: #1976d2; font-size: 13px;">
                                        Click "Create in Firebase Studio" to open Google's Project IDX with this prompt. 
                                        The AI will generate a complete website MVP for this business!
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="modal-actions" style="border-top: 1px solid #ddd; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center;">
                        <button class="btn-secondary" onclick="dashboardManagerInstance.closeWebsitePrompt()" style="padding: 10px 20px;">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                        <div style="display: flex; gap: 10px;">
                            <button class="btn-secondary" onclick="dashboardManagerInstance.copyWebsitePrompt()" style="padding: 10px 20px;">
                                <i class="fas fa-copy"></i> Copy Prompt
                            </button>
                            <button onclick="dashboardManagerInstance.openFirebaseStudio()" 
                                style="padding: 12px 25px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                       color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;
                                       display: flex; align-items: center; gap: 8px; font-size: 14px;
                                       box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);">
                                <i class="fas fa-rocket"></i> Create in Firebase Studio
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Remove any existing modal
        const existingModal = document.getElementById('website-prompt-overlay');
        if (existingModal) existingModal.remove();
        
        // Add to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    generateWebsitePrompt(business) {
        const businessName = business.name || 'Business';
        const location = business.city || business.address || 'the local area';
        const phone = business.phone || '';
        const rating = business.rating || '';
        const reviewCount = business.review_count || '';
        
        // Detect business type from name
        const nameLower = businessName.toLowerCase();
        let businessType = 'business';
        let specificFeatures = '';
        
        if (nameLower.includes('restaurant') || nameLower.includes('cafe') || nameLower.includes('kitchen') || 
            nameLower.includes('dining') || nameLower.includes('food') || nameLower.includes('bar') ||
            nameLower.includes('hotel') || nameLower.includes('grill')) {
            businessType = 'restaurant';
            specificFeatures = `
- Menu section with food categories (appetizers, main courses, desserts, beverages)
- Online table reservation system with date/time picker
- Photo gallery showcasing dishes and ambiance
- Customer reviews and testimonials section
- Special offers and daily specials banner
- Delivery/takeaway ordering information`;
        } else if (nameLower.includes('salon') || nameLower.includes('spa') || nameLower.includes('beauty')) {
            businessType = 'salon/spa';
            specificFeatures = `
- Services menu with pricing
- Online appointment booking system
- Staff/stylist profiles with photos
- Before/after gallery
- Customer testimonials
- Special packages and offers`;
        } else if (nameLower.includes('gym') || nameLower.includes('fitness') || nameLower.includes('yoga')) {
            businessType = 'fitness center';
            specificFeatures = `
- Class schedules and timetables
- Membership plans and pricing
- Trainer profiles
- Facilities showcase
- Online class booking
- Fitness tips blog section`;
        } else if (nameLower.includes('clinic') || nameLower.includes('hospital') || nameLower.includes('doctor') || nameLower.includes('dental')) {
            businessType = 'healthcare';
            specificFeatures = `
- Services/treatments offered
- Doctor/staff profiles with qualifications
- Online appointment booking
- Patient testimonials
- Health tips and articles
- Insurance information`;
        } else if (nameLower.includes('shop') || nameLower.includes('store') || nameLower.includes('mart')) {
            businessType = 'retail store';
            specificFeatures = `
- Product catalog with categories
- Featured products section
- Special offers and discounts
- Store location and hours
- Customer reviews
- Newsletter signup`;
        } else {
            specificFeatures = `
- Services/products offered
- About us section with company story
- Customer testimonials
- Contact form
- FAQ section
- Newsletter signup`;
        }

        return `Create a modern, professional, and fully responsive website for "${businessName}" - a ${businessType} located in ${location}.

## Business Information:
- **Business Name:** ${businessName}
- **Type:** ${businessType.charAt(0).toUpperCase() + businessType.slice(1)}
- **Location:** ${location}
${phone ? `- **Phone:** ${phone}` : ''}
${rating ? `- **Rating:** ${rating}/5 stars${reviewCount ? ` (${reviewCount} reviews)` : ''}` : ''}

## Website Requirements:

### Design & Aesthetics:
- Modern, clean, and professional design
- Mobile-first responsive layout
- Attractive hero section with high-quality imagery
- Consistent color scheme matching the ${businessType} industry
- Smooth animations and transitions
- Easy-to-read typography

### Essential Pages & Sections:
1. **Home Page:**
   - Eye-catching hero section with business tagline
   - Quick overview of services/offerings
   - Call-to-action buttons (Contact, Book Now, View Menu, etc.)
   - Customer testimonials carousel

2. **About Page:**
   - Business story and mission
   - Team/staff introduction
   - Why choose us section

3. **Services/Products Page:**
${specificFeatures}

4. **Contact Page:**
   - Contact form with validation
   - Business address with embedded Google Maps
   - Phone number and email
   - Operating hours
   - Social media links

5. **Footer:**
   - Quick links navigation
   - Contact information
   - Social media icons
   - Newsletter subscription
   - Copyright notice

### Technical Requirements:
- HTML5, CSS3, JavaScript
- Fully responsive (mobile, tablet, desktop)
- Fast loading and optimized images
- SEO-friendly structure
- Accessible (WCAG compliant)
- Cross-browser compatible

### Features to Include:
- Smooth scroll navigation
- Image lazy loading
- Contact form with validation
- Interactive elements (hover effects, animations)
- Social media integration
- Google Maps integration for location

Please create a complete, production-ready website that ${businessName} can use to establish their online presence and attract more customers.`;
    }
    
    copyWebsitePrompt() {
        const promptTextarea = document.getElementById('website-prompt-content');
        if (!promptTextarea) return;
        
        navigator.clipboard.writeText(promptTextarea.value).then(() => {
            this.showSuccessToast('Prompt copied to clipboard!');
        }).catch(err => {
            console.error('Failed to copy:', err);
            // Fallback for older browsers
            promptTextarea.select();
            document.execCommand('copy');
            this.showSuccessToast('Prompt copied to clipboard!');
        });
    }
    
    openFirebaseStudio() {
        const promptTextarea = document.getElementById('website-prompt-content');
        if (!promptTextarea) {
            this.showErrorToast('Prompt not found');
            return;
        }
        
        const prompt = promptTextarea.value.trim();
        if (!prompt) {
            this.showErrorToast('Please enter a prompt');
            return;
        }
        
        // Encode the prompt for URL
        const encodedPrompt = encodeURIComponent(prompt);
        
        // Firebase Studio / Project IDX URL with prompt
        // Using the new Gemini-powered project creation
        const firebaseStudioUrl = `https://idx.google.com/new/gemini?prompt=${encodedPrompt}`;
        
        // Open in new tab
        window.open(firebaseStudioUrl, '_blank');
        
        this.showSuccessToast('Opening Firebase Studio... The prompt will be automatically applied!');
        
        // Close the modal
        this.closeWebsitePrompt();
    }
    
    closeWebsitePrompt(event) {
        if (event && event.target.id !== 'website-prompt-overlay') return;
        
        const modal = document.getElementById('website-prompt-overlay');
        if (modal) modal.remove();
        
        this.currentWebsiteBusiness = null;
    }
    
    // ===== End Website Creation Prompt Methods =====

    // ===== Meeting Scheduling Methods =====
    
    showScheduleMeetingDialog(businessId, businessName) {
        const business = this.businesses.get(businessId);
        if (!business) {
            this.showErrorToast('Business not found');
            return;
        }
        
        console.log('Showing schedule meeting dialog for business:', business.name);
        
        // Get default date/time (tomorrow at 10:00 AM)
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        tomorrow.setHours(10, 0, 0, 0);
        
        const defaultDate = tomorrow.toISOString().split('T')[0];
        const defaultTime = '10:00';
        
        // Store for later use
        this.currentMeetingBusiness = business;
        
        // Create modal HTML
        const modalHtml = `
            <div class="modal-overlay" id="schedule-meeting-overlay" onclick="dashboardManagerInstance.closeScheduleMeetingDialog(event)">
                <div class="modal-dialog" style="max-width: 550px;" onclick="event.stopPropagation()">
                    <div class="modal-header" style="background: linear-gradient(135deg, #4285f4 0%, #34a853 100%); color: white; border-radius: 12px 12px 0 0;">
                        <h3 style="margin: 0; display: flex; align-items: center; gap: 10px;">
                            <i class="fas fa-calendar-plus"></i> Schedule Meeting with ${this.escapeHtml(business.name)}
                        </h3>
                        <button class="modal-close" onclick="dashboardManagerInstance.closeScheduleMeetingDialog()" style="color: white; background: rgba(255,255,255,0.2);">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                    <div class="modal-content" style="padding: 25px;">
                        <form id="schedule-meeting-form">
                            <div class="form-group" style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                    <i class="fas fa-heading" style="margin-right: 5px; color: #4285f4;"></i> Meeting Title
                                </label>
                                <input type="text" id="meeting-title" 
                                    value="Meeting with ${this.escapeHtml(business.name)}"
                                    style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                           font-size: 14px; transition: border-color 0.3s;"
                                    onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'">
                            </div>
                            
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                                <div class="form-group">
                                    <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                        <i class="fas fa-calendar" style="margin-right: 5px; color: #ea4335;"></i> Date
                                    </label>
                                    <input type="date" id="meeting-date" value="${defaultDate}"
                                        style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                               font-size: 14px; cursor: pointer;"
                                        onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'">
                                </div>
                                <div class="form-group">
                                    <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                        <i class="fas fa-clock" style="margin-right: 5px; color: #fbbc05;"></i> Time
                                    </label>
                                    <input type="time" id="meeting-time" value="${defaultTime}"
                                        style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                               font-size: 14px; cursor: pointer;"
                                        onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'">
                                </div>
                            </div>
                            
                            <div class="form-group" style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                    <i class="fas fa-hourglass-half" style="margin-right: 5px; color: #34a853;"></i> Duration
                                </label>
                                <select id="meeting-duration" 
                                    style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                           font-size: 14px; cursor: pointer; background: white;"
                                    onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'">
                                    <option value="15">15 minutes</option>
                                    <option value="30" selected>30 minutes</option>
                                    <option value="45">45 minutes</option>
                                    <option value="60">1 hour</option>
                                    <option value="90">1.5 hours</option>
                                    <option value="120">2 hours</option>
                                </select>
                            </div>
                            
                            <div class="form-group" style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                    <i class="fas fa-users" style="margin-right: 5px; color: #9c27b0;"></i> Attendee Email (optional)
                                </label>
                                <input type="email" id="meeting-attendee" 
                                    placeholder="Enter attendee's email address"
                                    value="${this.escapeHtml(business.email || '')}"
                                    style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                           font-size: 14px;"
                                    onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'">
                            </div>
                            
                            <div class="form-group" style="margin-bottom: 20px;">
                                <label style="display: block; margin-bottom: 8px; font-weight: 600; color: #2c3e50;">
                                    <i class="fas fa-align-left" style="margin-right: 5px; color: #ff5722;"></i> Meeting Description
                                </label>
                                <textarea id="meeting-description" rows="3"
                                    placeholder="Add meeting agenda or notes..."
                                    style="width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 8px; 
                                           font-size: 14px; resize: vertical; font-family: inherit;"
                                    onfocus="this.style.borderColor='#4285f4'" onblur="this.style.borderColor='#e0e0e0'"
                                >Discussion with ${this.escapeHtml(business.name)} regarding potential collaboration and project details.</textarea>
                            </div>
                            
                            <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); padding: 15px; border-radius: 8px; border-left: 4px solid #4caf50;">
                                <div style="display: flex; align-items: center; gap: 10px;">
                                    <i class="fab fa-google" style="color: #4caf50; font-size: 24px;"></i>
                                    <div>
                                        <strong style="color: #2e7d32;">Google Meet Link</strong>
                                        <p style="margin: 5px 0 0 0; color: #388e3c; font-size: 13px;">
                                            A Google Meet video conferencing link will be automatically generated and added to the calendar event.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </form>
                    </div>
                    <div class="modal-actions" style="border-top: 1px solid #ddd; padding: 15px 20px; display: flex; justify-content: flex-end; gap: 10px;">
                        <button class="btn-secondary" onclick="dashboardManagerInstance.closeScheduleMeetingDialog()" style="padding: 10px 20px;">
                            <i class="fas fa-times"></i> Cancel
                        </button>
                        <button onclick="dashboardManagerInstance.createGoogleMeeting()" 
                            style="padding: 12px 25px; background: linear-gradient(135deg, #4285f4 0%, #34a853 100%); 
                                   color: white; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;
                                   display: flex; align-items: center; gap: 8px; font-size: 14px;
                                   box-shadow: 0 4px 15px rgba(66, 133, 244, 0.4);">
                            <i class="fas fa-video"></i> Create Meeting & Add to Calendar
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Remove any existing modal
        const existingModal = document.getElementById('schedule-meeting-overlay');
        if (existingModal) existingModal.remove();
        
        // Add to body
        document.body.insertAdjacentHTML('beforeend', modalHtml);
    }
    
    async createGoogleMeeting() {
        const title = document.getElementById('meeting-title')?.value.trim();
        const date = document.getElementById('meeting-date')?.value;
        const time = document.getElementById('meeting-time')?.value;
        const duration = parseInt(document.getElementById('meeting-duration')?.value || '30');
        const attendee = document.getElementById('meeting-attendee')?.value.trim();
        const description = document.getElementById('meeting-description')?.value.trim();
        
        if (!title || !date || !time) {
            alert('Please fill in all required fields');
            return;
        }
        
        // Store business reference before any async operations
        const businessToSchedule = this.currentMeetingBusiness;
        if (!businessToSchedule) {
            alert('Business information not found');
            return;
        }
        
        // Show loading state on button
        const submitBtn = document.querySelector('#schedule-meeting-overlay button[onclick*="createGoogleMeeting"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Creating Meeting...';
        }
        
        // Create Google Calendar URL directly (works immediately)
        const startDateTime = new Date(`${date}T${time}:00`);
        const endDateTime = new Date(startDateTime.getTime() + duration * 60000);
        
        const formatGoogleDate = (d) => {
            return d.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
        };
        
        const startStr = formatGoogleDate(startDateTime);
        const endStr = formatGoogleDate(endDateTime);
        
        // Build Google Calendar URL with Meet conferencing
        let calendarUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE`;
        calendarUrl += `&text=${encodeURIComponent(title)}`;
        calendarUrl += `&dates=${startStr}/${endStr}`;
        calendarUrl += `&details=${encodeURIComponent(description + '\n\n---\nMeeting scheduled via LeadPilot')}`;
        
        if (attendee) {
            calendarUrl += `&add=${encodeURIComponent(attendee)}`;
        }
        // Add conference (Google Meet) flag
        calendarUrl += `&conf=1`;
        
        // Open Google Calendar in new tab IMMEDIATELY
        window.open(calendarUrl, '_blank');
        
        // Store meeting info
        const meetingInfo = {
            businessId: businessToSchedule.id,
            businessName: businessToSchedule.name,
            title: title,
            date: date,
            time: time,
            duration: duration,
            attendee: attendee,
            description: description,
            meet_link: '', // Will be available in Google Calendar
            calendar_link: calendarUrl,
            createdAt: new Date().toISOString(),
            status: 'scheduled'
        };
        
        // Add to scheduled meetings storage
        if (!this.scheduledMeetings) {
            this.scheduledMeetings = new Map();
        }
        this.scheduledMeetings.set(businessToSchedule.id, meetingInfo);
        
        // Update business status in local state
        const business = this.businesses.get(businessToSchedule.id);
        if (business) {
            business.status = 'meeting_scheduled';
            this.businesses.set(business.id, business);
        }
        
        // Move to Calendar column
        this.moveBusinessToCalendarColumn(businessToSchedule, meetingInfo);
        
        // Update stats
        this.updateStats();
        
        // Show success message
        this.showSuccessToast(`Meeting scheduled with ${businessToSchedule.name}! Complete in the Google Calendar tab.`);
        
        // Close the dialog
        this.closeScheduleMeetingDialog();
        
        // Also try to notify backend (non-blocking)
        try {
            fetch('/schedule_meeting', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    business_id: businessToSchedule.id,
                    title: title,
                    date: date,
                    time: time,
                    duration: duration,
                    attendee_email: attendee,
                    description: description
                })
            }).catch(err => console.log('Backend notification skipped:', err));
        } catch (e) {
            // Ignore backend errors - calendar already opened
        }
    }
    
    // Keep fallback for reference but primary method works directly
    createGoogleMeetingFallback(title, date, time, duration, attendee, description) {
        // Same as createGoogleMeeting - opens Calendar directly
        this.createGoogleMeeting();
    }
    
    closeScheduleMeetingDialog(event) {
        if (event && event.target.id !== 'schedule-meeting-overlay') return;
        
        const modal = document.getElementById('schedule-meeting-overlay');
        if (modal) modal.remove();
        
        this.currentMeetingBusiness = null;
    }
    
    moveBusinessToCalendarColumn(business, meetingInfo) {
        // Use the existing Calendar column (meeting-scheduled-content)
        const calendarContent = document.getElementById('meeting-scheduled-content');
        if (!calendarContent) {
            console.error('Calendar content column not found (id="meeting-scheduled-content")');
            return;
        }
        
        // Remove from Lead Manager column if present
        const existingCard = document.querySelector(`#lead-manager-content .business-card[data-business-id="${business.id}"]`);
        if (existingCard) {
            existingCard.remove();
        }
        
        // Also remove from any other column
        const anyExistingCard = document.querySelector(`.business-card[data-business-id="${business.id}"]`);
        if (anyExistingCard) {
            anyExistingCard.remove();
        }
        
        // Format meeting date and time
        const meetingDate = new Date(`${meetingInfo.date}T${meetingInfo.time}`);
        const formattedDate = meetingDate.toLocaleDateString('en-US', { 
            weekday: 'short', 
            month: 'short', 
            day: 'numeric',
            year: 'numeric'
        });
        const formattedTime = meetingDate.toLocaleTimeString('en-US', { 
            hour: '2-digit', 
            minute: '2-digit',
            hour12: true 
        });
        
        // Save meet link for later use
        if (meetingInfo.meet_link) {
            if (!this.savedMeetLinks) {
                this.savedMeetLinks = new Map();
            }
            this.savedMeetLinks.set(business.id, meetingInfo.meet_link);
        }
        
        // Create Calendar meeting card with professional styling
        const card = document.createElement('div');
        card.className = 'business-card compact meeting-card scheduled-meeting-card';
        card.setAttribute('data-business-id', business.id);
        card.setAttribute('data-meet-link', meetingInfo.meet_link || '');
        
        // Build Meet link section (only if we have a real link)
        const meetLinkSection = meetingInfo.meet_link ? `
            <div class="meet-link-section" style="margin-top: 12px; padding: 12px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 8px; border: 1px solid #a5d6a7;">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span style="font-size: 12px; font-weight: 600; color: #2e7d32; display: flex; align-items: center; gap: 6px;">
                        <i class="fab fa-google" style="font-size: 14px;"></i> Google Meet Ready
                    </span>
                    <span style="font-size: 10px; color: #388e3c; background: white; padding: 2px 8px; border-radius: 10px;">
                        <i class="fas fa-check-circle"></i> Auto-generated
                    </span>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button onclick="event.stopPropagation(); dashboardManagerInstance.joinMeeting('${business.id}')" 
                        style="flex: 2; padding: 10px 16px; background: linear-gradient(135deg, #34a853 0%, #1e8e3e 100%); color: white; 
                               border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600;
                               display: flex; align-items: center; justify-content: center; gap: 6px;
                               box-shadow: 0 2px 8px rgba(52, 168, 83, 0.3); transition: all 0.2s ease;">
                        <i class="fas fa-video"></i> Join Meeting
                    </button>
                    <button onclick="event.stopPropagation(); dashboardManagerInstance.copyMeetLinkDirect('${business.id}')" 
                        style="flex: 1; padding: 10px 12px; background: white; color: #34a853; 
                               border: 2px solid #34a853; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600;
                               display: flex; align-items: center; justify-content: center; gap: 4px; transition: all 0.2s ease;"
                        title="Copy Meet link to clipboard">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
            </div>
        ` : `
            <div class="meet-link-section" style="margin-top: 12px; padding: 12px; background: #fff8e1; border-radius: 8px; border: 1px dashed #ffb74d;">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <i class="fas fa-info-circle" style="color: #f57c00;"></i>
                    <span style="font-size: 12px; color: #e65100;">Meet link will be in your Google Calendar event</span>
                </div>
                <button onclick="event.stopPropagation(); window.open('https://calendar.google.com', '_blank')" 
                    style="width: 100%; padding: 10px 16px; background: linear-gradient(135deg, #4285f4 0%, #1a73e8 100%); color: white; 
                           border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600;
                           display: flex; align-items: center; justify-content: center; gap: 6px;">
                    <i class="fas fa-external-link-alt"></i> Open Google Calendar
                </button>
            </div>
        `;
        
        // Attendee info section
        const attendeeSection = meetingInfo.attendee ? `
            <div class="detail" style="margin-top: 8px;">
                <i class="fas fa-user" style="color: #9c27b0;"></i>
                <span style="font-size: 12px; color: #666;">${this.escapeHtml(meetingInfo.attendee)}</span>
            </div>
        ` : '';
        
        card.innerHTML = `
            <div class="business-header" style="margin-bottom: 12px;">
                <div class="business-title" style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 36px; height: 36px; background: linear-gradient(135deg, #4285f4 0%, #34a853 100%); 
                                border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <i class="fas fa-handshake" style="color: white; font-size: 16px;"></i>
                    </div>
                    <h4 style="margin: 0; font-size: 15px; font-weight: 600; color: #1a1a2e;">${this.escapeHtml(business.name)}</h4>
                </div>
                <span class="status-badge" style="background: linear-gradient(135deg, #4285f4 0%, #34a853 100%); color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600;">
                    <i class="fas fa-calendar-check" style="margin-right: 4px;"></i> Scheduled
                </span>
            </div>
            
            <div class="meeting-info" style="background: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 4px;">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-calendar-alt" style="color: #ea4335; font-size: 14px;"></i>
                        <span style="font-weight: 600; color: #333; font-size: 13px;">${formattedDate}</span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <i class="fas fa-clock" style="color: #4285f4; font-size: 14px;"></i>
                        <span style="font-weight: 600; color: #333; font-size: 13px;">${formattedTime}</span>
                    </div>
                </div>
                <div class="detail" style="margin-bottom: 4px;">
                    <i class="fas fa-hourglass-half" style="color: #fbbc05;"></i>
                    <span style="font-size: 12px; color: #666;">${meetingInfo.duration} minutes</span>
                </div>
                <div class="detail">
                    <i class="fas fa-tag" style="color: #9c27b0;"></i>
                    <span style="font-size: 12px; color: #666;">${this.escapeHtml(meetingInfo.title)}</span>
                </div>
                ${attendeeSection}
            </div>
            
            ${meetLinkSection}
        `;
        
        // Add to Calendar column with animation
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        calendarContent.insertBefore(card, calendarContent.firstChild);
        
        // Trigger animation
        requestAnimationFrame(() => {
            card.style.transition = 'all 0.3s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        });
        
        // Update stats
        this.updateStats();
        
        // Add activity log entry
        this.addActivityLogEntry('calendar', `Meeting scheduled with ${business.name} for ${formattedDate} at ${formattedTime}`, new Date().toISOString());
    }
    
    joinMeeting(businessId) {
        const meetLink = this.savedMeetLinks?.get(businessId);
        if (meetLink) {
            window.open(meetLink, '_blank');
        } else {
            this.showErrorToast('Meet link not available');
        }
    }
    
    copyMeetLinkDirect(businessId) {
        const meetLink = this.savedMeetLinks?.get(businessId);
        if (meetLink) {
            navigator.clipboard.writeText(meetLink).then(() => {
                this.showSuccessToast('Meet link copied to clipboard!');
            }).catch(() => {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = meetLink;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                this.showSuccessToast('Meet link copied!');
            });
        } else {
            this.showErrorToast('Meet link not available');
        }
    }
    
    openGoogleCalendar() {
        window.open('https://calendar.google.com/', '_blank');
    }
    
    copyMeetLink(businessId) {
        const meetLinkContainer = document.getElementById(`meet-link-${businessId}`);
        const meetLinkInput = document.getElementById(`meet-link-input-${businessId}`);
        
        if (!meetLinkContainer || !meetLinkInput) return;
        
        // Toggle visibility
        if (meetLinkContainer.style.display === 'none') {
            meetLinkContainer.style.display = 'block';
            
            // Check if we have a saved link
            const savedLink = this.savedMeetLinks?.get(businessId);
            if (savedLink) {
                // Copy to clipboard
                navigator.clipboard.writeText(savedLink).then(() => {
                    this.showSuccessToast('Meet link copied to clipboard!');
                }).catch(() => {
                    meetLinkInput.select();
                    document.execCommand('copy');
                    this.showSuccessToast('Meet link copied!');
                });
            } else {
                meetLinkInput.focus();
                this.showInfoToast('Paste your Google Meet link from the calendar event');
            }
        } else {
            meetLinkContainer.style.display = 'none';
        }
    }
    
    saveMeetLink(businessId) {
        const meetLinkInput = document.getElementById(`meet-link-input-${businessId}`);
        if (!meetLinkInput) return;
        
        const link = meetLinkInput.value.trim();
        if (!link) {
            this.showErrorToast('Please enter a Meet link');
            return;
        }
        
        // Validate it looks like a Google Meet link
        if (!link.includes('meet.google.com')) {
            this.showErrorToast('Please enter a valid Google Meet link');
            return;
        }
        
        // Save the link
        if (!this.savedMeetLinks) {
            this.savedMeetLinks = new Map();
        }
        this.savedMeetLinks.set(businessId, link);
        
        // Copy to clipboard
        navigator.clipboard.writeText(link).then(() => {
            this.showSuccessToast('Meet link saved and copied to clipboard!');
        }).catch(() => {
            this.showSuccessToast('Meet link saved!');
        });
        
        // Update button text to show it's saved
        const container = document.getElementById(`meet-link-${businessId}`);
        if (container) {
            container.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: space-between; padding: 5px;">
                    <span style="font-size: 12px; color: #34a853;">
                        <i class="fas fa-check-circle"></i> Link saved!
                    </span>
                    <button onclick="event.stopPropagation(); navigator.clipboard.writeText('${link}'); dashboardManagerInstance.showSuccessToast('Copied!')"
                        style="padding: 5px 10px; background: #34a853; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 11px;">
                        <i class="fas fa-copy"></i> Copy
                    </button>
                </div>
            `;
        }
    }
    
    showInfoToast(message) {
        this.showToast(message, 'info');
    }
    
    updateColumnCount(countId, count) {
        const countElement = document.getElementById(countId);
        if (countElement) {
            countElement.textContent = count;
        }
    }
    
    updateLeadManagerCount() {
        const leadManagerContent = document.getElementById('lead-manager-content');
        if (leadManagerContent) {
            const count = leadManagerContent.querySelectorAll('.business-card').length;
            this.updateColumnCount('lead-manager-count', count);
        }
    }
    
    // ===== End Meeting Scheduling Methods =====

    showSdrDialog(business) {
        console.log('Showing SDR dialog for business:', business.name);
        
        // Get the dialog element
        const dialog = document.getElementById('sdr-dialog-overlay');
        if (!dialog) {
            console.error('SDR dialog overlay not found!');
            return;
        }
        
        // Populate business preview
        const preview = document.getElementById('business-preview');
        if (!preview) {
            console.error('Business preview element not found!');
            return;
        }
        
        preview.innerHTML = `
            <h4>${this.escapeHtml(business.name)}</h4>
            ${business.city ? `<div class="detail"><i class="fas fa-map-marker-alt"></i><span>${this.escapeHtml(business.city)}</span></div>` : ''}
            ${business.phone ? `<div class="detail"><i class="fas fa-phone"></i><span>${this.escapeHtml(business.phone)}</span></div>` : ''}
            ${business.email ? `<div class="detail"><i class="fas fa-envelope"></i><span>${this.escapeHtml(business.email)}</span></div>` : ''}
            ${business.description ? `<div class="detail"><i class="fas fa-info-circle"></i><span>${this.escapeHtml(business.description)}</span></div>` : ''}
        `;
        
        // Store the business ID for later use
        const confirmBtn = document.getElementById('confirm-sdr-btn');
        if (!confirmBtn) {
            console.error('Confirm SDR button not found!');
            return;
        }
        confirmBtn.setAttribute('data-business-id', business.id);
        
        // Show the dialog by removing the hidden class
        dialog.classList.remove('hidden');
        
        console.log('Dialog should now be visible. Current display:', dialog.style.display);
        console.log('Dialog computed style:', window.getComputedStyle(dialog).display);
        
        // Initialize phone input with masking and button state
        this.initializePhoneInput();
        this.updateSendButtonState();
        
        // Add event listener for ESC key
        document.addEventListener('keydown', this.handleDialogKeydown);
    }
    
    closeSdrDialog() {
        console.log('DashboardManager.closeSdrDialog() called');
        const dialog = document.getElementById('sdr-dialog-overlay');
        console.log('Dialog element:', dialog);
        console.log('Dialog classes before:', dialog ? dialog.className : 'dialog not found');
        
        if (dialog) {
            // Hide the dialog by adding the hidden class
            dialog.classList.add('hidden');
            console.log('Hidden class added');
            console.log('Dialog classes after:', dialog.className);
            console.log('Dialog computed style after change:', window.getComputedStyle(dialog).display);
            
            // Reset button state if it exists
            const button = document.getElementById('confirm-sdr-btn');
            if (button) {
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-paper-plane"></i> Send to SDR';
                button.removeAttribute('data-business-id');
                console.log('Button state reset');
            }
        } else {
            console.error('Dialog element not found!');
        }
        
        // Remove event listener
        document.removeEventListener('keydown', this.handleDialogKeydown);
        console.log('Event listener removed');
    }
    
    handleDialogKeydown = (event) => {
        if (event.key === 'Escape') {
            this.closeSdrDialog();
        }
    }
    
    initializePhoneInput() {
        const phoneInput = document.getElementById('sdr-phone-input');
        if (!phoneInput) return;
        
        // Clear any existing value
        phoneInput.value = '';
        
        // Remove existing event listeners to avoid duplicates
        phoneInput.removeEventListener('input', this.handlePhoneInput);
        phoneInput.removeEventListener('blur', this.handlePhoneBlur);
        
        // Add phone number masking
        this.    handlePhoneInput = (e) => {
            let value = e.target.value.replace(/\D/g, ''); // Remove all non-digits
            let formattedValue = '';
            
            if (value.length > 0) {
                if (value.length <= 3) {
                    formattedValue = `(${value}`;
                } else if (value.length <= 6) {
                    formattedValue = `(${value.slice(0, 3)}) ${value.slice(3)}`;
                } else {
                    formattedValue = `(${value.slice(0, 3)}) ${value.slice(3, 6)}-${value.slice(6, 10)}`;
                }
            }
            
            e.target.value = formattedValue;
            
            // Update button state immediately
            this.updateSendButtonState();
        };
        
        // Add validation on blur
        this.handlePhoneBlur = (e) => {
            const value = e.target.value.replace(/\D/g, '');
            if (value.length !== 10) {
                e.target.setCustomValidity('Please enter a valid 10-digit US phone number');
            } else {
                e.target.setCustomValidity('');
            }
            this.updateSendButtonState();
        };
        
        phoneInput.addEventListener('input', this.handlePhoneInput);
        phoneInput.addEventListener('blur', this.handlePhoneBlur);
    }
    
    updateSendButtonState() {
        const phoneInput = document.getElementById('sdr-phone-input');
        const sendButton = document.getElementById('confirm-sdr-btn');
        const validationStatus = document.getElementById('phone-validation-status');
        const validationIcon = document.getElementById('phone-validation-icon');
        
        if (!phoneInput || !sendButton) return;
        
        const phoneValue = phoneInput.value.replace(/\D/g, '');
        // Simplified validation - just check if we have 10 digits (US phone number)
        const isValid = phoneValue.length === 10;
        
        sendButton.disabled = !isValid;
        
        if (isValid) {
            sendButton.innerHTML = '<i class="fas fa-paper-plane"></i> Send to SDR';
            phoneInput.classList.add('valid-input');
            phoneInput.classList.remove('invalid-input');
            
            if (validationStatus) {
                validationStatus.textContent = 'Valid number';
                validationStatus.className = 'validation-status valid';
            }
            
            if (validationIcon) {
                validationIcon.innerHTML = '✓';
                validationIcon.style.display = 'block';
                validationIcon.style.color = 'var(--success-color)';
            }
        } else {
            if (phoneValue.length > 0) {
                sendButton.innerHTML = '<i class="fas fa-paper-plane"></i> Enter Valid Phone';
                phoneInput.classList.add('invalid-input');
                phoneInput.classList.remove('valid-input');
                
                if (validationStatus) {
                    validationStatus.textContent = 'US format required (10 digits)';
                    validationStatus.className = 'validation-status invalid';
                }
                
                if (validationIcon) {
                    validationIcon.innerHTML = '✗';
                    validationIcon.style.display = 'block';
                    validationIcon.style.color = 'var(--danger-color)';
                }
            } else {
                sendButton.innerHTML = '<i class="fas fa-paper-plane"></i> Enter Phone Number';
                phoneInput.classList.remove('invalid-input');
                phoneInput.classList.remove('valid-input');
                
                if (validationStatus) {
                    validationStatus.textContent = '';
                    validationStatus.className = 'validation-status';
                }
                
                if (validationIcon) {
                    validationIcon.style.display = 'none';
                }
            }
        }
    }
    
    async confirmSendToSdr() {
        const button = document.getElementById('confirm-sdr-btn');
        const businessId = button.getAttribute('data-business-id');
        const phoneInput = document.getElementById('sdr-phone-input');
        
        // Button should already be disabled if phone is invalid, but double-check
        if (button.disabled) return;
        
        if (!businessId) {
            console.error('No business ID found');
            this.closeSdrDialog();
            return;
        }
        
        const phoneValue = phoneInput.value.replace(/\D/g, '');
        
        // Final validation (should not be needed due to real-time validation)
        if (phoneValue.length !== 10) {
            this.showErrorToast('Please enter a valid 10-digit US phone number');
            return;
        }
        
        // Disable the button and show loading
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
        
        try {
            const formData = new FormData();
            formData.append('business_id', businessId);
            formData.append('user_phone', phoneValue);
            
            const response = await fetch('/send_to_sdr', {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                // Handle HTTP errors
                const errorText = await response.text();
                let errorMessage = 'Failed to send to SDR agent';
                try {
                    const errorResult = JSON.parse(errorText);
                    errorMessage = errorResult.error || errorMessage;
                } catch (e) {
                    errorMessage = `Server error: ${response.status} ${response.statusText}`;
                }
                
                console.error('HTTP error sending to SDR:', errorMessage);
                this.showErrorToast(errorMessage);
                
                // Re-enable the button and close dialog
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-paper-plane"></i> Send to SDR';
                this.closeSdrDialog();
                return;
            }
            
            const result = await response.json();
            
            if (result.success) {
                console.log('Successfully sent to SDR:', result.message);
                // Update stats immediately
                this.updateStats();
                // Close the dialog on success - WebSocket will handle success message
                this.closeSdrDialog();
            } else {
                console.error('Failed to send to SDR:', result.error);
                this.showErrorToast(result.error || 'Failed to send to SDR agent');
                
                // Re-enable the button and close dialog
                button.disabled = false;
                button.innerHTML = '<i class="fas fa-paper-plane"></i> Send to SDR';
                this.closeSdrDialog();
            }
        } catch (error) {
            console.error('Network error sending to SDR:', error);
            this.showErrorToast('Network error: Failed to communicate with server');
            
            // Re-enable the button and close dialog
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-paper-plane"></i> Send to SDR';
            this.closeSdrDialog();
        }
    }
    
    showSuccessToast(message) {
        // Create toast notification
        const toast = document.createElement('div');
        toast.className = 'success-toast';
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #10b981;
            color: white;
            padding: 1rem 1.5rem;
            border-radius: 8px;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
            z-index: 10001;
            max-width: 400px;
            font-weight: 500;
        `;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 4000);
    }
}

// Global toast function
function showToast(message, type = 'info') {
    // Mute error and warning toasts - only log to console
    if (type === 'error' || type === 'warning') {
        console.log(`${type.charAt(0).toUpperCase() + type.slice(1)} toast muted:`, message);
        return;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let backgroundColor;
    switch(type) {
        case 'success':
            backgroundColor = '#10b981';
            break;
        default:
            backgroundColor = '#3b82f6';
    }
    
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${backgroundColor};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        z-index: 10001;
        max-width: 400px;
        font-weight: 500;
        opacity: 0;
        transform: translateX(100%);
        transition: all 0.3s ease;
    `;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    // Trigger animation
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    });
    
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 300);
    }, 4000);
}

// Global functions
function resetDashboard() {
    if (confirm('Are you sure you want to reset the dashboard and start a new search?')) {
        fetch('/reset', { method: 'POST' })
            .then(response => {
                if (response.ok) {
                    window.location.href = '/';
                } else {
                    console.error('Failed to reset dashboard');
                }
            })
            .catch(error => {
                console.error('Error resetting dashboard:', error);
            });
    }
}

// Global dialog functions
let dashboardManagerInstance = null;

function closeSdrDialog() {
    console.log('Global closeSdrDialog called');
    if (dashboardManagerInstance) {
        console.log('Calling dashboardManagerInstance.closeSdrDialog()');
        dashboardManagerInstance.closeSdrDialog();
    } else {
        console.error('dashboardManagerInstance is null!');
    }
}

function confirmSendToSdr() {
    if (dashboardManagerInstance) {
        dashboardManagerInstance.confirmSendToSdr();
    }
}

// Research dialog global functions
function closeResearchDialog() {
    if (dashboardManagerInstance) {
        dashboardManagerInstance.closeResearchDialog();
    }
}

function proceedToSdr() {
    if (dashboardManagerInstance) {
        dashboardManagerInstance.proceedToSdr();
    }
}

// Direct SDR send function (skips phone number step)
function sendToSdrDirect() {
    if (dashboardManagerInstance) {
        dashboardManagerInstance.sendToSdrDirect();
    }
}

function toggleLog() {
    const logElement = document.querySelector('.activity-log');
    const toggleButton = document.querySelector('.toggle-log i');
    
    if (logElement.classList.contains('collapsed')) {
        logElement.classList.remove('collapsed');
        toggleButton.className = 'fas fa-chevron-up';
    } else {
        logElement.classList.add('collapsed');
        toggleButton.className = 'fas fa-chevron-down';
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing dashboard...');
    dashboardManagerInstance = new DashboardManager();
});

// Handle page visibility changes to manage WebSocket connection
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        console.log('Page hidden, WebSocket may be paused');
    } else {
        console.log('Page visible, ensuring WebSocket is connected');
    }
});

// Human Input Modal Functions
let currentHumanInputRequest = null;

function showHumanInputDialog(requestData) {
    console.log('Showing human input dialog:', requestData);
    
    currentHumanInputRequest = requestData;
    
    // Populate the prompt
    const promptTextarea = document.getElementById('human-input-prompt');
    if (promptTextarea) {
        promptTextarea.value = requestData.prompt || '';
    }
    
    // Show the modal
    const overlay = document.getElementById('human-input-dialog-overlay');
    if (overlay) {
        overlay.classList.remove('hidden');
        
        // Add fade-in animation
        overlay.style.opacity = '0';
        setTimeout(() => {
            overlay.style.opacity = '1';
        }, 10);
    }
    
    // Clear previous URL input
    const urlInput = document.getElementById('website-url-input');
    if (urlInput) {
        urlInput.value = '';
    }
    
    // Focus on URL input
    setTimeout(() => {
        if (urlInput) {
            urlInput.focus();
        }
    }, 300);
}

function closeHumanInputDialog() {
    const overlay = document.getElementById('human-input-dialog-overlay');
    if (overlay) {
        overlay.classList.add('hidden');
        overlay.style.opacity = '0';
    }
    
    currentHumanInputRequest = null;
}

function copyPromptToClipboard() {
    const promptTextarea = document.getElementById('human-input-prompt');
    if (promptTextarea) {
        promptTextarea.select();
        
        // Use modern clipboard API if available, fallback to execCommand
        if (navigator.clipboard) {
            navigator.clipboard.writeText(promptTextarea.value).then(() => {
                showToast('Prompt copied to clipboard!', 'success');
            }).catch(() => {
                // Fallback to execCommand
                document.execCommand('copy');
                showToast('Prompt copied to clipboard!', 'success');
            });
        } else {
            document.execCommand('copy');
            showToast('Prompt copied to clipboard!', 'success');
        }
    }
}

function openFirebaseStudio() {
    // Get the prompt from the dialog
    const promptTextarea = document.getElementById('human-input-prompt');
    if (!promptTextarea) {
        // If no prompt available, just open Google IDX
        window.open('https://idx.google.com/new/gemini', '_blank');
        showToast('Opening Google IDX...', 'success');
        return;
    }
    
    const prompt = promptTextarea.value.trim();
    if (!prompt) {
        // If prompt is empty, open without prompt
        window.open('https://idx.google.com/new/gemini', '_blank');
        showToast('Opening Google IDX...', 'success');
        return;
    }
    
    // Encode the prompt for URL
    const encodedPrompt = encodeURIComponent(prompt);
    
    // Open Google IDX with the prompt
    const idxUrl = `https://idx.google.com/new/gemini?prompt=${encodedPrompt}`;
    window.open(idxUrl, '_blank');
    
    showToast('Opening Google IDX with website creation prompt...', 'success');
}

async function submitWebsiteUrl() {
    if (!currentHumanInputRequest) {
        showToast('No active request found', 'error');
        return;
    }
    
    const urlInput = document.getElementById('website-url-input');
    const submitBtn = document.getElementById('submit-website-url-btn');
    
    if (!urlInput.value.trim()) {
        showToast('Please enter a website URL', 'error');
        urlInput.focus();
        return;
    }
    
    // Validate URL format
    try {
        new URL(urlInput.value.trim());
    } catch (e) {
        showToast('Please enter a valid URL', 'error');
        urlInput.focus();
        return;
    }
    
    // Show loading state
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
    
    try {
        const response = await fetch(`/api/human-input/${currentHumanInputRequest.request_id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                request_id: currentHumanInputRequest.request_id,
                response: urlInput.value.trim()
            })
        });
        
        if (response.ok) {
            await response.json(); // Response received but not used
            showToast('Website URL submitted successfully!', 'success');
            // Close the human input dialog here to prevent it from reappearing if no WebSocket event arrives
            closeHumanInputDialog();
        } else {
            const error = await response.json();
            showToast(`Error: ${error.message || 'Failed to submit URL'}`, 'error');
        }
    } catch (error) {
        console.error('Error submitting website URL:', error);
        showToast('Error submitting URL. Please try again.', 'error');
    } finally {
        // Reset button state
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fas fa-check"></i> Submit URL';
    }
}

// Handle ESC key for human input modal and keyboard shortcuts
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const overlay = document.getElementById('human-input-dialog-overlay');
        if (overlay && !overlay.classList.contains('hidden')) {
            closeHumanInputDialog();
        }
    }
    
    // Keyboard shortcut: Ctrl+Shift+L to trigger Lead Manager
    if (event.ctrlKey && event.shiftKey && event.key === 'L') {
        event.preventDefault();
        console.log('🔥 Keyboard shortcut triggered: Ctrl+Shift+L - Triggering Lead Manager');
        triggerLeadManager();
    }
});

// Function to trigger lead manager agent
async function triggerLeadManager() {
    console.log('🤖 Triggering Lead Manager agent...');
    
    try {
        const response = await fetch('/trigger_lead_manager', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                trigger: 'manual',
                timestamp: new Date().toISOString()
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage = 'Failed to trigger Lead Manager agent';
            try {
                const errorResult = JSON.parse(errorText);
                errorMessage = errorResult.error || errorMessage;
            } catch (e) {
                errorMessage = `Server error: ${response.status} ${response.statusText}`;
            }
            throw new Error(errorMessage);
        }
        
        const result = await response.json();
        console.log('✅ Lead Manager agent triggered successfully:', result);
        showToast('Lead Manager agent triggered successfully!', 'success');
        
        // Add activity log entry
        if (window.dashboard) {
            window.dashboard.addActivityLogEntry('lead_manager', 'Agent triggered manually', new Date().toISOString());
        }
        
    } catch (error) {
        console.error('❌ Error triggering Lead Manager agent:', error);
        showToast(`Error: ${error.message}`, 'error');
    }
}

// Test function to manually trigger human input dialog
function testHumanInputDialog() {
    const testData = {
        request_id: 'test-' + Date.now(),
        prompt: 'Create a professional website for a local bakery called "Sweet Dreams Bakery". The website should include:\n\n1. A welcoming homepage with beautiful images of baked goods\n2. An about page telling the story of the bakery\n3. A menu page showcasing different products (breads, pastries, cakes)\n4. Contact information and location\n5. Online ordering capability\n6. Modern, clean design with warm colors\n7. Mobile-responsive layout\n\nThe target audience is local residents who appreciate fresh, artisanal baked goods. The tone should be warm, inviting, and family-friendly.',
        input_type: 'website_creation',
        timestamp: new Date().toISOString()
    };
    
    showHumanInputDialog(testData);
}