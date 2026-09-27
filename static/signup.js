document.addEventListener('DOMContentLoaded', () => {
  const logoInput = document.getElementById('company-logo');
  const logoUploadText = document.getElementById('logoUploadText');
  const logoUploadInfo = document.getElementById('logoUploadInfo');

  if (logoInput && logoUploadText && logoUploadInfo) {
    logoInput.addEventListener('change', () => {
      const file = logoInput.files && logoInput.files[0];

      if (file) {
        logoUploadText.textContent = file.name;
        logoUploadInfo.textContent = `${(file.size / 1024).toFixed(1)} KB selected`;
      } else {
        logoUploadText.textContent = 'Upload Logo';
        logoUploadInfo.textContent = 'PNG, JPG or SVG (Max. 2MB)';
      }
    });
  }
});