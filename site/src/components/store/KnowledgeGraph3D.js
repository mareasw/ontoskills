import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

let activeDispose = null;

window.__ontoskills_create_graph = (container, { nodes, edges, prefix, onNavigate }) => {
  // Dispose previous scene
  window.__ontoskills_dispose_graph?.();

  if (!nodes.length) return;

  const width = container.clientWidth || 400;
  const height = 400;

  // ─── Scene ───
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 1000);
  camera.position.set(0, 0, 30);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(width, height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);
  container.appendChild(renderer.domElement);

  // ─── Controls ───
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.6;
  controls.minDistance = 10;
  controls.maxDistance = 80;

  // Stop auto-rotate on user interaction
  renderer.domElement.addEventListener('pointerdown', () => { controls.autoRotate = false; });

  // ─── Lights ───
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const pointLight = new THREE.PointLight(0x52c7e8, 1.5, 100);
  pointLight.position.set(20, 20, 20);
  scene.add(pointLight);
  const pointLight2 = new THREE.PointLight(0x85f496, 0.8, 100);
  pointLight2.position.set(-20, -10, 15);
  scene.add(pointLight2);

  // ─── Force-directed 3D layout ───
  const positions = layoutForce3D(nodes, edges);

  // ─── Node meshes ───
  const nodeColorMap = {
    development: 0x52c7e8,
    productivity: 0x85f496,
  };
  const defaultColor = 0x9763e1;
  const highlightColor = 0x52c7e8;

  const nodeMeshes = [];
  for (const n of nodes) {
    const p = positions[n.id];
    const isHighlighted = !!n.isHighlighted;
    const color = isHighlighted ? highlightColor : (nodeColorMap[n.category] || defaultColor);
    const radius = isHighlighted ? 1.4 : 0.9;

    const geo = new THREE.SphereGeometry(Math.max(radius, 0.1), 32, 32);
    const mat = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: isHighlighted ? 0.4 : 0.15,
      roughness: 0.3,
      metalness: 0.2,
      transparent: true,
      opacity: 0.9,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(p.x, p.y, p.z);
    mesh.userData = { skillId: n.id, qualifiedId: n.qualifiedId };
    scene.add(mesh);
    nodeMeshes.push(mesh);

    // Glow for highlighted
    if (isHighlighted) {
      const glowGeo = new THREE.SphereGeometry(Math.max(radius * 2.5, 0.1), 32, 32);
      const glowMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.08 });
      const glow = new THREE.Mesh(glowGeo, glowMat);
      glow.position.copy(mesh.position);
      scene.add(glow);
    }

    // Label
    const label = createTextSprite(n.label, isHighlighted ? '#f5f5f5' : '#8a8a8a');
    label.position.set(p.x, p.y - radius - 0.8, p.z);
    label.scale.set(5, 2.5, 1);
    scene.add(label);
  }

  // ─── Edge lines ───
  for (const e of edges) {
    const s = positions[e.source], t = positions[e.target];
    if (!s || !t) continue;
    const points = [new THREE.Vector3(s.x, s.y, s.z), new THREE.Vector3(t.x, t.y, t.z)];
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const mat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.12 });
    scene.add(new THREE.Line(geo, mat));

    // Arrow cone at midpoint
    const dir = new THREE.Vector3(t.x - s.x, t.y - s.y, t.z - s.z).normalize();
    const mid = new THREE.Vector3((s.x + t.x) / 2, (s.y + t.y) / 2, (s.z + t.z) / 2);
    const coneGeo = new THREE.ConeGeometry(Math.max(0.2, 0.2), 0.6, 8);
    const coneMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.2 });
    const cone = new THREE.Mesh(coneGeo, coneMat);
    cone.position.copy(mid);
    // Align cone to direction
    const up = new THREE.Vector3(0, 1, 0);
    const quat = new THREE.Quaternion().setFromUnitVectors(up, dir);
    cone.setRotationFromQuaternion(quat);
    scene.add(cone);
  }

  // ─── Raycasting ───
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let hoveredMesh = null;

  renderer.domElement.addEventListener('mousemove', (e) => {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(nodeMeshes);
    if (hits.length > 0) {
      renderer.domElement.style.cursor = 'pointer';
      if (hoveredMesh !== hits[0].object) {
        if (hoveredMesh) hoveredMesh.material.emissiveIntensity = hoveredMesh.userData.origEmissive || 0.15;
        hoveredMesh = hits[0].object;
        hoveredMesh.userData.origEmissive = hoveredMesh.userData.origEmissive ?? hoveredMesh.material.emissiveIntensity;
        hoveredMesh.material.emissiveIntensity = 0.6;
      }
    } else {
      renderer.domElement.style.cursor = 'grab';
      if (hoveredMesh) {
        hoveredMesh.material.emissiveIntensity = hoveredMesh.userData.origEmissive || 0.15;
        hoveredMesh = null;
      }
    }
  });

  renderer.domElement.addEventListener('click', (e) => {
    const rect = renderer.domElement.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(mouse, camera);
    const hits = raycaster.intersectObjects(nodeMeshes);
    if (hits.length > 0 && onNavigate) {
      onNavigate(hits[0].object.userData.qualifiedId);
    }
  });

  // ─── Animate ───
  let animId;
  function animate() {
    animId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  // ─── Resize ───
  const onResize = () => {
    const w = container.clientWidth || 400;
    camera.aspect = w / height;
    camera.updateProjectionMatrix();
    renderer.setSize(w, height);
  };
  window.addEventListener('resize', onResize);

  // ─── Dispose ───
  activeDispose = () => {
    cancelAnimationFrame(animId);
    window.removeEventListener('resize', onResize);
    controls.dispose();
    renderer.dispose();
    scene.traverse((obj) => {
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
        else obj.material.dispose();
      }
      if (obj.texture) obj.texture.dispose();
    });
    renderer.domElement.remove();
    activeDispose = null;
  };
};

window.__ontoskills_dispose_graph = () => {
  if (activeDispose) activeDispose();
};

// ─── 3D Force-directed layout ───

function layoutForce3D(nodes, edges) {
  const positions = {};
  const n = nodes.length;
  if (!n) return positions;

  // Initialize on a sphere
  const R = Math.max(n * 1.8, 8);
  nodes.forEach((node, i) => {
    const phi = Math.acos(-1 + (2 * i) / n);
    const theta = Math.sqrt(n * Math.PI) * phi;
    positions[node.id] = {
      x: R * Math.cos(theta) * Math.sin(phi),
      y: R * Math.sin(theta) * Math.sin(phi),
      z: R * Math.cos(phi),
    };
  });

  const iterations = 180;
  const k = R * 1.2; // ideal spring length

  for (let iter = 0; iter < iterations; iter++) {
    const temp = 1 - iter / iterations;

    // Charge repulsion
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = positions[nodes[i].id], b = positions[nodes[j].id];
        const dx = a.x - b.x, dy = a.y - b.y, dz = a.z - b.z;
        const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 0.1);
        const force = (k * k) / dist;
        const fx = (dx / dist) * force * temp * 0.4;
        const fy = (dy / dist) * force * temp * 0.4;
        const fz = (dz / dist) * force * temp * 0.4;
        a.x += fx; a.y += fy; a.z += fz;
        b.x -= fx; b.y -= fy; b.z -= fz;
      }
    }

    // Link attraction
    for (const e of edges) {
      const s = positions[e.source], t = positions[e.target];
      if (!s || !t) continue;
      const dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 0.1);
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force * temp * 0.2;
      const fy = (dy / dist) * force * temp * 0.2;
      const fz = (dz / dist) * force * temp * 0.2;
      s.x += fx; s.y += fy; s.z += fz;
      t.x -= fx; t.y -= fy; t.z -= fz;
    }

    // Center gravity
    for (const node of nodes) {
      const p = positions[node.id];
      p.x *= 0.98;
      p.y *= 0.98;
      p.z *= 0.98;
    }
  }

  return positions;
}

// ─── Text sprite ───

function createTextSprite(text, color = '#8a8a8a') {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 128;
  const ctx = canvas.getContext('2d');
  ctx.font = 'bold 24px monospace';
  ctx.fillStyle = color;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 128, 64);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false });
  return new THREE.Sprite(mat);
}
