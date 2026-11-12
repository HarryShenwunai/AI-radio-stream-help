'use strict';
let capture = null, state = 'awaiting_user';
const video = document.getElementById('preview'), start = document.getElementById('start');
const stop = document.getElementById('stop'), status = document.getElementById('state');
const canvas = document.createElement('canvas');
function stopCapture() {
  for (const track of capture?.getTracks() || []) track.stop();
  capture = null; video.srcObject = null; state = 'stopped';
  canvas.width = canvas.height = 0;
  status.textContent = '已停止'; start.disabled = true; stop.disabled = true;
}
start.addEventListener('click', async () => {
  if (state !== 'awaiting_user' || !navigator.userActivation.isActive) return;
  start.disabled = true;
  try {
    capture = await navigator.mediaDevices.getDisplayMedia({ video: { width: { max: 1600 }, height: { max: 900 }, frameRate: { ideal: 5, max: 10 } }, audio: false });
    if (state === 'stopped') { stopCapture(); return; }
    video.srcObject = capture; await video.play(); state = 'active'; stop.disabled = false; status.textContent = '仅在本机预览';
    capture.getVideoTracks()[0].addEventListener('ended', stopCapture, { once: true });
  } catch { stopCapture(); state = 'failed'; status.textContent = '未取得共享内容，请关闭后重试'; }
});
stop.addEventListener('click', stopCapture); window.addEventListener('pagehide', stopCapture);
window.captureFrame = () => {
  if (state !== 'active' || !video.videoWidth || !video.videoHeight) return { state };
  if (!capture.getVideoTracks().some(track => track.readyState === 'live')) { stopCapture(); return { state }; }
  const scale = Math.min(1,1600/video.videoWidth,900/video.videoHeight);
  canvas.width = Math.max(1,Math.round(video.videoWidth*scale)); canvas.height = Math.max(1,Math.round(video.videoHeight*scale));
  canvas.getContext('2d',{alpha:false}).drawImage(video,0,0,canvas.width,canvas.height);
  const result = { state, image_base64: canvas.toDataURL('image/jpeg',.78).split(',')[1], width: canvas.width, height: canvas.height };
  canvas.width = canvas.height = 0; return result;
};
