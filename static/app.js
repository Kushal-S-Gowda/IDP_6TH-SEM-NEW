// =============================================
// FLOODSENSE PRO — UNIFIED JAVASCRIPT
// Enhanced Navigation & Interactions
// =============================================

// === Navigation Dropdown Functionality ===
function fsToggleDrop(button) {
  const dropdown = button.nextElementSibling;
  const isOpen = dropdown.classList.contains('open');
  
  // Close all other dropdowns
  document.querySelectorAll('.ndrop.open').forEach(drop => {
    drop.classList.remove('open');
    const btn = drop.previousElementSibling;
    if (btn && btn !== button) {
      btn.classList.remove('open');
      const arrow = btn.querySelector('.ndrop-arrow');
      if (arrow) arrow.style.transform = 'rotate(0deg)';
    }
  });
  
  // Toggle current dropdown
  if (!isOpen) {
    dropdown.classList.add('open');
    button.classList.add('open');
    const arrow = button.querySelector('.ndrop-arrow');
    if (arrow) arrow.style.transform = 'rotate(180deg)';
  } else {
    dropdown.classList.remove('open');
    button.classList.remove('open');
  }
}

// === Close dropdowns when clicking outside ===
document.addEventListener('click', function(event) {
  if (!event.target.matches('.ndrop-btn, .ndrop-btn *')) {
    document.querySelectorAll('.ndrop.open').forEach(dropdown => {
      dropdown.classList.remove('open');
      const button = dropdown.previousElementSibling;
      if (button) {
        button.classList.remove('open');
        const arrow = button.querySelector('.ndrop-arrow');
        if (arrow) arrow.style.transform = 'rotate(0deg)';
      }
    });
  }
});

// === Clock Functionality ===
function updateClock() {
  const now = new Date();
  const timeString = now.toLocaleTimeString('en-IN', { 
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
  const clockElement = document.getElementById('clock');
  if (clockElement) {
    clockElement.textContent = timeString;
  }
}

// === Initialize on DOM Load ===
document.addEventListener('DOMContentLoaded', function() {
  // Start clock
  updateClock();
  setInterval(updateClock, 1000);
  
  // Add hover effects to cards
  const cards = document.querySelectorAll('.card, .risk-card, .info-card, .contact-item');
  cards.forEach(card => {
    card.addEventListener('mouseenter', function() {
      this.style.transform = 'translateY(-2px)';
    });
    card.addEventListener('mouseleave', function() {
      this.style.transform = 'translateY(0)';
    });
  });
  
  // Add smooth scroll behavior
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });
  
  // Add loading states for buttons
  const buttons = document.querySelectorAll('.btn');
  buttons.forEach(button => {
    button.addEventListener('click', function() {
      if (!this.classList.contains('loading')) {
        const originalText = this.innerHTML;
        this.classList.add('loading');
        this.innerHTML = '<span class="spinner"></span> Loading...';
        this.disabled = true;
        
        // Simulate loading completion (remove in production)
        setTimeout(() => {
          this.classList.remove('loading');
          this.innerHTML = originalText;
          this.disabled = false;
        }, 1500);
      }
    });
  });
});

// === Utility Functions ===
function showNotification(message, type = 'info') {
  const notification = document.createElement('div');
  notification.className = `alert alert-${type}`;
  notification.style.cssText = `
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 10000;
    padding: 16px 24px;
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
    transform: translateX(400px);
    transition: transform 0.3s ease;
  `;
  notification.textContent = message;
  
  document.body.appendChild(notification);
  
  // Animate in
  setTimeout(() => {
    notification.style.transform = 'translateX(0)';
  }, 100);
  
  // Auto remove after 5 seconds
  setTimeout(() => {
    notification.style.transform = 'translateX(400px)';
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }, 5000);
}

function animateValue(element, start, end, duration) {
  const startTime = performance.now();
  
  function update(currentTime) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const current = start + (end - start) * progress;
    element.textContent = current.toFixed(1);
    
    if (progress < 1) {
      requestAnimationFrame(update);
    }
  }
  
  requestAnimationFrame(update);
}

// === Keyboard Navigation ===
document.addEventListener('keydown', function(event) {
  // Escape key closes dropdowns
  if (event.key === 'Escape') {
    document.querySelectorAll('.ndrop.show').forEach(dropdown => {
      dropdown.classList.remove('show');
      const button = dropdown.previousElementSibling;
      if (button) {
        button.classList.remove('active');
        const arrow = button.querySelector('.ndrop-arrow');
        if (arrow) arrow.style.transform = 'rotate(0deg)';
      }
    });
  }
  
  // Alt + number shortcuts for navigation
  if (event.altKey) {
    switch(event.key) {
      case '1':
        window.location.href = '/';
        break;
      case '2':
        window.location.href = '/citizen';
        break;
      case '3':
        window.location.href = '/authority';
        break;
      case '4':
        window.location.href = '/early-warning';
        break;
      case '5':
        window.location.href = '/alert-center';
        break;
    }
  }
});

// === Performance Monitoring ===
window.addEventListener('load', function() {
  console.log('FloodSense Pro - Dashboard Loaded');
  
  // Monitor page load performance
  if (window.performance && window.performance.timing) {
    const loadTime = window.performance.timing.loadEventEnd - window.performance.timing.navigationStart;
    console.log(`Page load time: ${loadTime}ms`);
  }
});

// === PWA Support (disabled - no service worker file) ===
// serviceWorker registration removed to prevent console errors