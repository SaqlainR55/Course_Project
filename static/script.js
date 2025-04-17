const recordButton = document.getElementById('record');
const stopButton = document.getElementById('stop');
const audioElement = document.getElementById('audio');
const uploadForm = document.getElementById('uploadForm');
const audioDataInput = document.getElementById('audioData');
const timerDisplay = document.getElementById('timer');

let mediaRecorder;
let audioChunks = [];
let startTime;
let timerInterval;

function formatTime(time) {
  const minutes = Math.floor(time / 60);
  const seconds = Math.floor(time % 60);
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

recordButton.addEventListener('click', () => {
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

      audioChunks = []; // reset buffer
      mediaRecorder.start();

      startTime = Date.now();
      timerInterval = setInterval(() => {
        const elapsedTime = Math.floor((Date.now() - startTime) / 1000);
        timerDisplay.textContent = formatTime(elapsedTime);
      }, 1000);

      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = () => {
        clearInterval(timerInterval);
        timerDisplay.textContent = '00:00';

        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append('audio_data', audioBlob, 'recorded_audio.wav');

        fetch('/upload', {
          method: 'POST',
          body: formData
        })
          .then(response => {
            if (!response.ok) throw new Error('Upload failed');
            location.reload(); // refresh to show results
          })
          .catch(error => {
            console.error('Upload error:', error);
            alert('Upload failed. Try again.');
          });

        // Stop all audio tracks to close mic
        stream.getTracks().forEach(track => track.stop());
      };

      recordButton.disabled = true;
      stopButton.disabled = false;
    })
    .catch(error => {
      console.error('Mic access error:', error);
      alert('Could not access microphone.');
    });
});

stopButton.addEventListener('click', () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
  }

  recordButton.disabled = false;
  stopButton.disabled = true;
});

// Disable stop button initially
stopButton.disabled = true;
