// Runs in a hidden window the main process controls. The camera is open only for the moment it takes
// to grab one frame, so the camera light is on briefly and never during the whole exam.
interface Window {
  capture?: () => Promise<string>;
}

(() => {
  const video = document.getElementById("v") as HTMLVideoElement;
  const canvas = document.getElementById("c") as HTMLCanvasElement;
  const WARM_UP_MS = 700; // let auto-exposure settle, otherwise the first frame is dark

  window.capture = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 } },
      audio: false,
    });
    try {
      video.srcObject = stream;
      await video.play();
      await new Promise((resolve) => setTimeout(resolve, WARM_UP_MS));
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      canvas.getContext("2d")!.drawImage(video, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/jpeg", 0.7);
    } finally {
      stream.getTracks().forEach((track) => track.stop());
      video.srcObject = null;
    }
  };
})();
