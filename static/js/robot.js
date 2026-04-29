/* Eye tracking for robot logo — pupils follow the cursor.
   Any <circle class="eye" data-cx="..." data-cy="..."> inside an SVG works. */

(function () {
  const MAX_OFFSET = 1.0;       // pupil travel limit, in SVG units (eye socket radius is 2.2)
  const SOFTEN_DIST = 220;      // px — beyond this distance, pupils max out

  function track(e) {
    const eyes = document.querySelectorAll("svg .eye");
    if (!eyes.length) return;
    eyes.forEach(eye => {
      const svg = eye.ownerSVGElement;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const vb = svg.viewBox.baseVal;
      const baseX = parseFloat(eye.dataset.cx);
      const baseY = parseFloat(eye.dataset.cy);
      const screenX = rect.left + (baseX / vb.width) * rect.width;
      const screenY = rect.top + (baseY / vb.height) * rect.height;
      const dx = e.clientX - screenX;
      const dy = e.clientY - screenY;
      const dist = Math.hypot(dx, dy) || 1;
      const t = Math.min(1, dist / SOFTEN_DIST);
      const offX = (dx / dist) * MAX_OFFSET * t;
      const offY = (dy / dist) * MAX_OFFSET * t;
      eye.setAttribute("cx", baseX + offX);
      eye.setAttribute("cy", baseY + offY);
    });
  }

  document.addEventListener("mousemove", track, { passive: true });

  // Subtle idle blink: every ~5s scale eyes briefly via a CSS-friendly attribute swap.
  setInterval(() => {
    if (knockedOut) return;
    document.querySelectorAll("svg .eye").forEach(eye => {
      const r = parseFloat(eye.getAttribute("r")) || 1;
      eye.setAttribute("r", r * 0.2);
      setTimeout(() => eye.setAttribute("r", r), 120);
    });
  }, 5200);

  // Easter egg: 10 fast clicks → X eyes + battery disappears
  const SVG_NS = "http://www.w3.org/2000/svg";
  let clickTimes = [];
  let knockedOut = false;
  let ouchTimeout = null;

  // Show "ouch" message near robot
  function showOuch(event) {
    // Remove existing ouch if present
    const existingOuch = document.querySelector(".robot-ouch");
    if (existingOuch) existingOuch.remove();

    // Make robot sad temporarily
    makeSad();

    // Create ouch element
    const ouch = document.createElement("div");
    ouch.className = "robot-ouch";
    ouch.textContent = "Ouch!";
    ouch.style.position = "fixed";
    ouch.style.left = event.clientX + "px";
    ouch.style.top = (event.clientY - 30) + "px";
    ouch.style.color = "#ff0000";
    ouch.style.fontWeight = "bold";
    ouch.style.fontSize = "18px";
    ouch.style.pointerEvents = "none";
    ouch.style.zIndex = "10000";
    ouch.style.animation = "fadeOut 0.8s ease-out";
    document.body.appendChild(ouch);

    // Remove after animation
    setTimeout(() => ouch.remove(), 800);
  }

  function makeSad() {
    // Change all robot smiles to sad mouths
    document.querySelectorAll("svg.robot-svg").forEach(svg => {
      const mouth = svg.querySelector('path');
      if (mouth && !mouth.classList.contains("robot-sad") && !mouth.classList.contains("robot-dead-mouth")) {
        // Only save original if not already saved
        if (!mouth.dataset.originalD) {
          mouth.dataset.originalD = mouth.getAttribute("d");
        }
        mouth.setAttribute("d", "M 8 16.5 Q 12 14.5 16 16.5");
        mouth.classList.add("robot-sad");
      }
    });

    // Restore smile after a moment (only if not dead)
    setTimeout(() => {
      if (knockedOut) return; // Don't restore if robot is knocked out
      document.querySelectorAll("svg.robot-svg .robot-sad").forEach(mouth => {
        const originalD = mouth.dataset.originalD;
        if (originalD) {
          mouth.setAttribute("d", originalD);
          mouth.classList.remove("robot-sad");
          delete mouth.dataset.originalD; // Clear after restoring
        }
      });
    }, 600);
  }

  function knockOut() {
    knockedOut = true;
    
    // Get bigger robot SVG (in welcome card) for battery launch
    const bigRobot = document.querySelector(".welcome-icon svg.robot-svg");
    const robotRect = bigRobot ? bigRobot.getBoundingClientRect() : null;
    
    // Make batteries disappear and eyes turn to X
    document.querySelectorAll("svg.robot-svg").forEach(svg => {
      // Hide battery (red circle on antenna - not the eyes)
      const battery = svg.querySelector('circle[cx="12"][cy="1.3"]');
      if (battery) {
        battery.style.display = "none";
        battery.classList.add("robot-battery");
      }

      // Replace eyes with X
      const eyes = svg.querySelectorAll(".eye");
      if (!eyes.length) return;
      eyes.forEach(eye => {
        const cx = parseFloat(eye.dataset.cx);
        const cy = parseFloat(eye.dataset.cy);
        const size = 1.6;
        const g = document.createElementNS(SVG_NS, "g");
        g.classList.add("x-eye");
        g.dataset.replacing = eye.getAttribute("data-cx");
        for (const [x1, y1, x2, y2] of [
          [cx - size, cy - size, cx + size, cy + size],
          [cx - size, cy + size, cx + size, cy - size],
        ]) {
          const line = document.createElementNS(SVG_NS, "line");
          line.setAttribute("x1", x1); line.setAttribute("y1", y1);
          line.setAttribute("x2", x2); line.setAttribute("y2", y2);
          line.setAttribute("stroke", "#ff5a5a");
          line.setAttribute("stroke-width", "0.7");
          line.setAttribute("stroke-linecap", "round");
          g.appendChild(line);
        }
        eye.style.display = "none";
        eye.parentNode.insertBefore(g, eye.nextSibling);
      });

      // Make mouth a straight line (dead/neutral)
      const mouth = svg.querySelector('path');
      if (mouth) {
        // Only save original if not already saved (to preserve the smile, not a temporary sad state)
        if (!mouth.dataset.originalD) {
          mouth.dataset.originalD = mouth.getAttribute("d");
        }
        mouth.setAttribute("d", "M 8 16 L 16 16");
        mouth.classList.remove("robot-sad"); // Clear any sad state
        mouth.classList.add("robot-dead-mouth");
      }

      // Create drop zone indicator
      const batteryArea = document.createElementNS(SVG_NS, "circle");
      batteryArea.setAttribute("cx", "12");
      batteryArea.setAttribute("cy", "1.3");
      batteryArea.setAttribute("r", "1.5");
      batteryArea.setAttribute("fill", "transparent");
      batteryArea.setAttribute("stroke", "#666");
      batteryArea.setAttribute("stroke-width", "0.3");
      batteryArea.setAttribute("stroke-dasharray", "0.5,0.5");
      batteryArea.classList.add("battery-restore-area");
      svg.appendChild(batteryArea);
    });

    // Create draggable battery that slides away from robot
    if (robotRect) {
      createFlyingBattery(robotRect);
    }
  }

  function createFlyingBattery(robotRect) {
    // Get the bigger robot to find the battery circle position
    const bigRobot = document.querySelector(".welcome-icon svg.robot-svg");
    const batteryCircle = bigRobot ? bigRobot.querySelector('circle[cx="12"][cy="1.3"]') : null;
    
    // Calculate exact position of battery circle
    let startX = robotRect.left + robotRect.width / 2 - 20;
    let startY = robotRect.top;
    
    if (batteryCircle) {
      const vb = bigRobot.viewBox.baseVal;
      const circleCx = parseFloat(batteryCircle.getAttribute("cx"));
      const circleCy = parseFloat(batteryCircle.getAttribute("cy"));
      startX = robotRect.left + (circleCx / vb.width) * robotRect.width - 20;
      startY = robotRect.top + (circleCy / vb.height) * robotRect.height - 30;
    }
    
    const battery = document.createElement("div");
    battery.className = "flying-battery";
    battery.innerHTML = `
      <svg viewBox="0 0 40 60" style="width:40px;height:60px;">
        <!-- Battery body -->
        <rect x="5" y="8" width="30" height="45" rx="2" fill="#ff7a2f" stroke="#d96527" stroke-width="2"/>
        <!-- Positive terminal -->
        <rect x="15" y="0" width="10" height="8" rx="1" fill="#ff7a2f" stroke="#d96527" stroke-width="2"/>
        <!-- Plus sign -->
        <line x1="20" y1="20" x2="20" y2="30" stroke="white" stroke-width="3" stroke-linecap="round"/>
        <line x1="15" y1="25" x2="25" y2="25" stroke="white" stroke-width="3" stroke-linecap="round"/>
      </svg>
    `;
    battery.style.position = "fixed";
    battery.style.left = startX + "px";
    battery.style.top = startY + "px";
    battery.style.cursor = "grab";
    battery.style.zIndex = "10000";
    battery.style.transition = "all 0.8s ease-out";
    document.body.appendChild(battery);

    // Slide battery to the right and down from robot
    const slideDistance = 200;
    setTimeout(() => {
      battery.style.left = (parseFloat(battery.style.left) + slideDistance) + "px";
      battery.style.top = (parseFloat(battery.style.top) + slideDistance * 0.5) + "px";
      battery.style.transform = "rotate(15deg)";
    }, 50);

    // Make it draggable after it slides
    setTimeout(() => {
      battery.style.transition = "none";
      makeDraggable(battery);
    }, 900);
  }

  function makeDraggable(element) {
    let isDragging = false;
    let startX, startY, initialX, initialY;
    let lastPositions = []; // Track positions for velocity calculation

    element.addEventListener("mousedown", startDrag);
    
    function startDrag(e) {
      isDragging = true;
      element.style.cursor = "grabbing";
      startX = e.clientX;
      startY = e.clientY;
      const rect = element.getBoundingClientRect();
      initialX = rect.left;
      initialY = rect.top;
      lastPositions = [{ x: e.clientX, y: e.clientY, time: Date.now() }];
      
      document.addEventListener("mousemove", drag);
      document.addEventListener("mouseup", stopDrag);
      e.preventDefault();
    }

    function drag(e) {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      
      // Calculate new position
      let newX = initialX + dx;
      let newY = initialY + dy;
      
      // Keep within viewport bounds
      const batteryWidth = 40;
      const batteryHeight = 60;
      newX = Math.max(0, Math.min(newX, window.innerWidth - batteryWidth));
      newY = Math.max(0, Math.min(newY, window.innerHeight - batteryHeight));
      
      element.style.left = newX + "px";
      element.style.top = newY + "px";
      
      // Track last few positions for velocity
      lastPositions.push({ x: e.clientX, y: e.clientY, time: Date.now() });
      if (lastPositions.length > 5) lastPositions.shift();
    }

    function stopDrag(e) {
      if (!isDragging) return;
      isDragging = false;
      element.style.cursor = "grab";
      document.removeEventListener("mousemove", drag);
      document.removeEventListener("mouseup", stopDrag);
      
      // Calculate velocity
      const velocity = calculateVelocity(lastPositions);
      const speed = Math.sqrt(velocity.vx * velocity.vx + velocity.vy * velocity.vy);
      
      // If thrown fast enough, animate the throw
      if (speed > 0.5) {
        throwBattery(element, velocity, e.clientX, e.clientY);
      } else {
        // Just dropped - check if on robot
        checkBatteryDrop(element, e.clientX, e.clientY);
      }
    }
    
    function calculateVelocity(positions) {
      if (positions.length < 2) return { vx: 0, vy: 0 };
      const first = positions[0];
      const last = positions[positions.length - 1];
      const dt = (last.time - first.time) / 1000; // seconds
      if (dt === 0) return { vx: 0, vy: 0 };
      return {
        vx: (last.x - first.x) / dt,
        vy: (last.y - first.y) / dt
      };
    }
  }

  function throwBattery(battery, velocity, startX, startY) {
    battery.style.cursor = "default";
    const startTime = Date.now();
    const maxDuration = 3000; // ms - max flight time
    const batteryWidth = 40;
    const batteryHeight = 60;
    const bounceDamping = 0.6; // Energy loss on bounce
    const friction = 0.97; // Friction per frame - slows battery smoothly
    
    // Current velocity (will change on bounce)
    let vx = velocity.vx;
    let vy = velocity.vy;
    let lastX = startX;
    let lastY = startY;
    let lastTime = startTime;
    
    function animate() {
      const now = Date.now();
      const elapsed = now - startTime;
      const dt = (now - lastTime) / 1000; // time since last frame in seconds
      lastTime = now;
      
      // Apply friction smoothly
      vx *= friction;
      vy *= friction;
      
      // Stop if too much time has passed or velocity is very low
      if (elapsed >= maxDuration || (Math.abs(vx) < 30 && Math.abs(vy) < 30)) {
        battery.style.cursor = "grab";
        checkBatteryDrop(battery, parseFloat(battery.style.left), parseFloat(battery.style.top));
        return;
      }
      
      // Calculate new position
      let x = lastX + vx * dt;
      let y = lastY + vy * dt;
      
      // Check for wall collisions and bounce
      const maxX = window.innerWidth - batteryWidth;
      const maxY = window.innerHeight - batteryHeight;
      
      // Left or right wall
      if (x <= 0) {
        x = 0;
        vx = Math.abs(vx) * bounceDamping; // Reverse and dampen
      } else if (x >= maxX) {
        x = maxX;
        vx = -Math.abs(vx) * bounceDamping; // Reverse and dampen
      }
      
      // Top or bottom wall
      if (y <= 0) {
        y = 0;
        vy = Math.abs(vy) * bounceDamping; // Reverse and dampen
      } else if (y >= maxY) {
        y = maxY;
        vy = -Math.abs(vy) * bounceDamping; // Reverse and dampen
      }
      
      lastX = x;
      lastY = y;
      
      battery.style.left = x + "px";
      battery.style.top = y + "px";
      
      // Rotate based on velocity
      const totalTime = elapsed / 1000;
      const rotation = (vx * totalTime * 0.5);
      battery.style.transform = `rotate(${rotation}deg)`;
      
      // Check if hitting robot during flight
      const robots = document.querySelectorAll("svg.robot-svg");
      let hitRobot = false;
      robots.forEach(svg => {
        const rect = svg.getBoundingClientRect();
        if (x >= rect.left - 30 && x <= rect.right + 30 &&
            y >= rect.top - 30 && y <= rect.bottom + 30) {
          hitRobot = true;
        }
      });
      
      if (hitRobot) {
        battery.style.cursor = "grab";
        battery.style.transition = "all 0.3s ease-out";
        battery.style.opacity = "0";
        battery.style.transform = "scale(0.5)";
        setTimeout(() => {
          battery.remove();
          reviveRobot();
        }, 300);
        return;
      }
      
      requestAnimationFrame(animate);
    }
    
    animate();
  }

  function checkBatteryDrop(battery, x, y) {
    // Find all robot SVGs
    const robots = document.querySelectorAll("svg.robot-svg");
    let dropped = false;

    robots.forEach(svg => {
      const rect = svg.getBoundingClientRect();
      // Check if battery is dropped near robot
      if (x >= rect.left - 30 && x <= rect.right + 30 &&
          y >= rect.top - 30 && y <= rect.bottom + 30) {
        dropped = true;
      }
    });

    if (dropped) {
      // Successful drop - restore robot
      battery.style.transition = "all 0.3s ease-out";
      battery.style.opacity = "0";
      battery.style.transform = "scale(0.5)";
      setTimeout(() => {
        battery.remove();
        reviveRobot();
      }, 300);
    }
  }

  function reviveRobot() {
    // Remove X eyes
    document.querySelectorAll("svg .x-eye").forEach(g => g.remove());
    
    // Show eyes again
    document.querySelectorAll("svg .eye").forEach(eye => { eye.style.display = ""; });
    
    // Show battery again
    document.querySelectorAll("svg .robot-battery").forEach(battery => {
      battery.style.display = "";
    });
    
    // Restore mouth to smile
    document.querySelectorAll("svg .robot-dead-mouth").forEach(mouth => {
      const originalD = mouth.dataset.originalD;
      if (originalD) {
        mouth.setAttribute("d", originalD);
        mouth.classList.remove("robot-dead-mouth");
        mouth.classList.remove("robot-sad"); // Clear any sad state
        delete mouth.dataset.originalD; // Clear so it can be saved fresh next time
      }
    });
    
    // Remove restore areas
    document.querySelectorAll(".battery-restore-area").forEach(area => area.remove());
    
    // Remove any flying batteries
    document.querySelectorAll(".flying-battery").forEach(battery => battery.remove());
    
    knockedOut = false;
    clickTimes = [];
  }

  // Click handler for robot SVGs
  document.addEventListener("click", (e) => {
    // Check if clicking on a robot SVG or its children
    const robotSvg = e.target.closest("svg.robot-svg");
    if (!robotSvg) return;

    // If knocked out, don't count clicks (need to restore battery)
    if (knockedOut) return;

    const now = Date.now();
    clickTimes.push(now);
    // Keep only clicks within the last 3 seconds
    clickTimes = clickTimes.filter(t => now - t < 3000);
    
    // Check if this will knock out the robot
    if (clickTimes.length >= 10) {
      knockOut();
    } else {
      // Only show "ouch" and sad face if not knocking out
      showOuch(e);
    }
  });

  // Add CSS animation for ouch and flying battery
  if (!document.querySelector("#robot-ouch-style")) {
    const style = document.createElement("style");
    style.id = "robot-ouch-style";
    style.textContent = `
      @keyframes fadeOut {
        0% { opacity: 1; transform: translateY(0); }
        100% { opacity: 0; transform: translateY(-20px); }
      }
      .flying-battery {
        filter: drop-shadow(0 2px 8px rgba(255, 122, 47, 0.5));
        user-select: none;
      }
      .flying-battery:active {
        filter: drop-shadow(0 4px 12px rgba(255, 122, 47, 0.8));
      }
    `;
    document.head.appendChild(style);
  }
})();
