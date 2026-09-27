document.addEventListener('DOMContentLoaded', () => {

  const totalEl =
    document.getElementById('totalAmount');

  const totalInputEl =
    document.getElementById('totalAmountInput');

  const form =
    document.querySelector('form');

  const formMessage =
    document.getElementById('formMessage');

  const submitButton =
    form?.querySelector('button[type="submit"]');


  const itemsContainer =
    document.getElementById('itemsContainer');

  const itemRowTemplate =
    document.getElementById('itemRowTemplate');

  const addItemButton =
    document.getElementById('addItemButton');


  let isSubmitting = false;


  /* --------------------------------
     FORM MESSAGE
  --------------------------------- */

  function showFormMessage(message, success = false) {

    if (!formMessage) {
      return;
    }

    formMessage.textContent = message;

    formMessage.style.color =
      success ? '#28a745' : '#dc3545';

  }


  function clearFormMessage() {

    if (!formMessage) {
      return;
    }

    formMessage.textContent = '';
    formMessage.style.color = '';

  }


  /* --------------------------------
     ITEM TOTAL CALCULATION
  --------------------------------- */

  function updateTotals() {

    if (!itemsContainer || !totalEl) {
      return;
    }

    let grandTotal = 0;


    itemsContainer
      .querySelectorAll('.item-row')
      .forEach((row) => {

        const qtyInput =
          row.querySelector('.item-qty');

        const priceInput =
          row.querySelector('.item-price');

        const lineTotalEl =
          row.querySelector('.item-line-total');


        const qty =
          parseFloat(qtyInput?.value) || 0;

        const price =
          parseFloat(priceInput?.value) || 0;


        const lineTotal =
          qty * price;


        if (lineTotalEl) {

          lineTotalEl.textContent =
            lineTotal.toFixed(2);

        }


        grandTotal += lineTotal;

      });


    totalEl.textContent =
      grandTotal.toFixed(2);


    if (totalInputEl) {

      totalInputEl.value =
        grandTotal.toFixed(2);

    }

  }


  /* --------------------------------
     ADD ITEM
  --------------------------------- */

  function addItemRow() {

    if (!itemRowTemplate || !itemsContainer) {
      return;
    }


    const clone =
      itemRowTemplate.content.cloneNode(true);


    const row =
      clone.querySelector('.item-row');


    if (!row) {
      return;
    }


    row
      .querySelectorAll('.item-qty, .item-price')
      .forEach((input) => {

        input.addEventListener(
          'input',
          updateTotals
        );

        input.addEventListener(
          'change',
          updateTotals
        );

      });


    const removeButton =
      row.querySelector('.remove-item-button');


    removeButton?.addEventListener(
      'click',
      () => {

        const rows =
          itemsContainer.querySelectorAll('.item-row');


        if (rows.length > 1) {

          row.remove();

          updateTotals();

          clearFormMessage();

        } else {

          showFormMessage(
            'At least one item is required.'
          );

        }

      }
    );


    itemsContainer.appendChild(row);

  }


  addItemButton?.addEventListener(
    'click',
    () => {

      addItemRow();

      clearFormMessage();

    }
  );


  /* --------------------------------
     START WITH ONE ITEM
  --------------------------------- */

  addItemRow();

  updateTotals();


  /* --------------------------------
     FILE UPLOAD
  --------------------------------- */

  const uploadZone =
    document.getElementById('uploadZone');

  const uploadButton =
    document.getElementById('uploadButton');

  const fileInput =
    document.getElementById('fileInput');

  const fileList =
    document.getElementById('fileList');


  let selectedFiles = [];

  let syncingFiles = false;


  function formatFileSize(bytes) {

    if (bytes < 1024) {
      return `${bytes} B`;
    }


    if (bytes < 1024 * 1024) {

      return `${(bytes / 1024).toFixed(1)} KB`;

    }


    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  }


  function updateFileInput() {

    if (!fileInput) {
      return;
    }


    const dataTransfer =
      new DataTransfer();


    selectedFiles.forEach((file) => {

      dataTransfer.items.add(file);

    });


    syncingFiles = true;

    fileInput.files =
      dataTransfer.files;

    syncingFiles = false;

  }


  function renderFileList() {

    if (!fileList) {
      return;
    }


    fileList.innerHTML = '';


    if (selectedFiles.length === 0) {
      return;
    }


    selectedFiles.forEach(
      (file, index) => {

        const fileItem =
          document.createElement('div');

        fileItem.className =
          'file-item';


        const fileDetails =
          document.createElement('div');

        fileDetails.className =
          'file-details';


        const fileName =
          document.createElement('span');

        fileName.className =
          'file-name-text';

        fileName.textContent =
          file.name;


        const fileSize =
          document.createElement('span');

        fileSize.className =
          'file-size';

        fileSize.textContent =
          formatFileSize(file.size);


        const removeButton =
          document.createElement('button');

        removeButton.type =
          'button';

        removeButton.className =
          'remove-file-button';

        removeButton.textContent =
          'Remove';


        removeButton.addEventListener(
          'click',
          () => {

            selectedFiles.splice(
              index,
              1
            );


            updateFileInput();

            renderFileList();

            clearFormMessage();

          }
        );


        fileDetails.appendChild(
          fileName
        );

        fileDetails.appendChild(
          fileSize
        );


        fileItem.appendChild(
          fileDetails
        );

        fileItem.appendChild(
          removeButton
        );


        fileList.appendChild(
          fileItem
        );

      }
    );

  }


  function addFiles(files) {

    const newFiles =
      Array.from(files || []);


    newFiles.forEach((file) => {

      const alreadySelected =
        selectedFiles.some(
          (selectedFile) =>
            selectedFile.name === file.name &&
            selectedFile.size === file.size
        );


      if (!alreadySelected) {

        selectedFiles.push(file);

      }

    });


    updateFileInput();

    renderFileList();

  }


  if (uploadButton && fileInput) {

    uploadButton.addEventListener(
      'click',
      () => {

        fileInput.click();

      }
    );


    fileInput.addEventListener(
      'change',
      () => {

        if (syncingFiles) {
          return;
        }

        addFiles(fileInput.files);

      }
    );


    ['dragenter', 'dragover']
      .forEach((eventName) => {

        uploadZone?.addEventListener(
          eventName,
          (event) => {

            event.preventDefault();

            uploadZone.classList.add(
              'dragover'
            );

          }
        );

      });


    ['dragleave', 'drop']
      .forEach((eventName) => {

        uploadZone?.addEventListener(
          eventName,
          (event) => {

            event.preventDefault();

            uploadZone.classList.remove(
              'dragover'
            );

          }
        );

      });


    uploadZone?.addEventListener(
      'drop',
      (event) => {

        if (
          !event.dataTransfer?.files?.length
        ) {
          return;
        }


        addFiles(
          event.dataTransfer.files
        );

      }
    );

  }


  /* --------------------------------
     TERMS AND CONDITIONS
  --------------------------------- */

  const editTermsBtn =
    document.getElementById('editTermsBtn');

  const termsListEl =
    document.getElementById('termsList');

  const saveTermsBtn =
    document.getElementById('saveTermsBtn');

  const cancelTermsBtn =
    document.getElementById('cancelTermsBtn');

  const termsDataInput =
    document.getElementById('termsData');


  const defaultTerms = [

    'This estimate is valid for 7 days from the date of issue.',

    '100% advance to be paid for the PO to become valid.',

    'One year return to bench warranty for all products.',

    'Free shipping by road or rail within India.'

  ];


  let terms = [];

  let originalHTML = '';


  function loadTerms() {

    try {

      if (
        termsDataInput &&
        termsDataInput.value
      ) {

        const parsed =
          JSON.parse(
            termsDataInput.value
          );


        if (
          Array.isArray(parsed) &&
          parsed.length
        ) {

          terms = parsed;

          return;

        }

      }

    } catch (error) {

      // Use default terms if saved data is invalid

    }


    terms =
      defaultTerms.slice();

  }


  function renderTerms() {

    if (!termsListEl) {
      return;
    }


    termsListEl.innerHTML = '';


    terms.forEach((term) => {

      const li =
        document.createElement('li');

      li.textContent =
        term;

      termsListEl.appendChild(li);

    });


    if (termsDataInput) {

      termsDataInput.value =
        JSON.stringify(terms);

    }


    termsListEl.contentEditable =
      'false';


    if (saveTermsBtn) {

      saveTermsBtn.hidden =
        true;

    }


    if (cancelTermsBtn) {

      cancelTermsBtn.hidden =
        true;

    }


    if (editTermsBtn) {

      editTermsBtn.disabled =
        false;

    }

  }


  editTermsBtn?.addEventListener(
    'click',
    () => {

      if (!termsListEl) {
        return;
      }


      originalHTML =
        termsListEl.innerHTML;


      termsListEl.contentEditable =
        'true';


      termsListEl.focus();


      if (saveTermsBtn) {

        saveTermsBtn.hidden =
          false;

      }


      if (cancelTermsBtn) {

        cancelTermsBtn.hidden =
          false;

      }


      if (editTermsBtn) {

        editTermsBtn.disabled =
          true;

      }

    }
  );


  saveTermsBtn?.addEventListener(
    'click',
    () => {

      if (!termsListEl) {
        return;
      }


      const text =
        termsListEl.innerText || '';


      const lines =
        text
          .split('\n')
          .map(
            (text) => text.trim()
          )
          .filter(Boolean);


      terms = lines;


      if (termsDataInput) {

        termsDataInput.value =
          JSON.stringify(terms);

      }


      renderTerms();

    }
  );


  cancelTermsBtn?.addEventListener(
    'click',
    () => {

      if (!termsListEl) {
        return;
      }


      termsListEl.innerHTML =
        originalHTML;


      termsListEl.contentEditable =
        'false';


      if (saveTermsBtn) {

        saveTermsBtn.hidden =
          true;

      }


      if (cancelTermsBtn) {

        cancelTermsBtn.hidden =
          true;

      }


      if (editTermsBtn) {

        editTermsBtn.disabled =
          false;

      }

    }
  );


  loadTerms();

  renderTerms();


  /* --------------------------------
     PREVIOUS BUTTON
  --------------------------------- */

  const previousButton =
    document.getElementById(
      'previousPageButton'
    );


  previousButton?.addEventListener(
    'click',
    () => {

      history.back();

    }
  );


  /* --------------------------------
     DATE VALIDATION
  --------------------------------- */

  const quotationDate =
    document.getElementById(
      'quotationDate'
    );


  const quotationExpiry =
    document.getElementById(
      'quotationExpiry'
    );


  function validateDates() {

    if (
      !quotationDate ||
      !quotationExpiry
    ) {

      return true;

    }


    if (!quotationDate.value) {

      showFormMessage(
        'Please select the quotation date.'
      );


      quotationDate.focus();

      return false;

    }


    if (!quotationExpiry.value) {

      showFormMessage(
        'Please select the quotation expiry date.'
      );


      quotationExpiry.focus();

      return false;

    }


    const quotationDateValue =
      new Date(
        `${quotationDate.value}T00:00:00`
      );


    const expiryDateValue =
      new Date(
        `${quotationExpiry.value}T00:00:00`
      );


    if (
      expiryDateValue <
      quotationDateValue
    ) {

      showFormMessage(
        'Expiry date cannot be before the quotation date.'
      );


      quotationExpiry.focus();


      quotationExpiry.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });


      return false;

    }


    return true;

  }


  /* --------------------------------
     SET MINIMUM EXPIRY DATE
  --------------------------------- */

  quotationDate?.addEventListener(
    'change',
    () => {

      clearFormMessage();


      if (
        quotationExpiry &&
        quotationDate.value
      ) {

        quotationExpiry.min =
          quotationDate.value;


        if (
          quotationExpiry.value &&
          quotationExpiry.value <
          quotationDate.value
        ) {

          quotationExpiry.value =
            '';

        }

      }

    }
  );


  quotationExpiry?.addEventListener(
    'change',
    () => {

      clearFormMessage();

    }
  );


  if (
    quotationDate &&
    quotationExpiry &&
    quotationDate.value
  ) {

    quotationExpiry.min =
      quotationDate.value;

  }


  /* --------------------------------
     STATE VALIDATION
  --------------------------------- */

  function validateStates() {

    const companyState =
      document.getElementById(
        'states'
      );


    const customerState =
      document.getElementById(
        'statesCustomer'
      );


    if (!companyState?.value) {

      showFormMessage(
        'Please select the Company State.'
      );


      companyState?.focus();

      return false;

    }


    if (!customerState?.value.trim()) {

      showFormMessage(
        'Please select the Customer State.'
      );


      customerState?.focus();

      return false;

    }


    return true;

  }


  document
    .getElementById('states')
    ?.addEventListener(
      'change',
      clearFormMessage
    );


  document
    .getElementById('statesCustomer')
    ?.addEventListener(
      'change',
      clearFormMessage
    );


  /* --------------------------------
     ITEM VALIDATION
  --------------------------------- */

  function validateItems() {

    if (!itemsContainer) {
      return true;
    }


    const rows =
      itemsContainer.querySelectorAll(
        '.item-row'
      );


    if (rows.length === 0) {

      showFormMessage(
        'At least one item is required.'
      );


      addItemButton?.focus();

      return false;

    }


    for (const row of rows) {

      const itemName =
        row.querySelector(
          '.item-name'
        );


      const quantity =
        row.querySelector(
          '.item-qty'
        );


      const unitPrice =
        row.querySelector(
          '.item-price'
        );


      if (!itemName?.value.trim()) {

        showFormMessage(
          'Please enter an item name.'
        );


        itemName?.focus();

        return false;

      }


      const qty =
        parseFloat(
          quantity?.value
        );


      if (
        !quantity?.value ||
        Number.isNaN(qty) ||
        qty <= 0
      ) {

        showFormMessage(
          'Item quantity must be greater than 0.'
        );


        quantity?.focus();

        return false;

      }


      const price =
        parseFloat(
          unitPrice?.value
        );


      if (
        !unitPrice?.value ||
        Number.isNaN(price) ||
        price < 0
      ) {

        showFormMessage(
          'Unit price cannot be empty or negative.'
        );


        unitPrice?.focus();

        return false;

      }

    }


    return true;

  }


  /* --------------------------------
     CUSTOMER VALIDATION
  --------------------------------- */

  function validateCustomer() {

    const customerName =
      document.getElementById(
        'customerName'
      );


    const billingAddress =
      document.getElementById(
        'billingAddress'
      );


    const companyName =
      document.getElementById(
        'companyName'
      );


    const email =
      document.getElementById(
        'email'
      );


    const phoneNo =
      document.getElementById(
        'phoneNo'
      );


    if (!customerName?.value.trim()) {

      showFormMessage(
        'Please enter the customer name.'
      );


      customerName?.focus();

      return false;

    }


    if (!billingAddress?.value.trim()) {

      showFormMessage(
        'Please enter the billing address.'
      );


      billingAddress?.focus();

      return false;

    }


    if (!companyName?.value.trim()) {

      showFormMessage(
        'Please enter the customer company name.'
      );


      companyName?.focus();

      return false;

    }


    if (!email?.value.trim()) {

      showFormMessage(
        'Please enter the email address.'
      );


      email?.focus();

      return false;

    }


    if (!email.checkValidity()) {

      showFormMessage(
        'Please enter a valid email address.'
      );


      email?.focus();

      return false;

    }


    if (!phoneNo?.value.trim()) {

      showFormMessage(
        'Please enter the phone number.'
      );


      phoneNo?.focus();

      return false;

    }


    if (
      !/^[0-9]{10}$/.test(
        phoneNo.value.trim()
      )
    ) {

      showFormMessage(
        'Phone number must contain exactly 10 digits.'
      );


      phoneNo?.focus();

      return false;

    }


    return true;

  }


  /* --------------------------------
     AGREEMENT VALIDATION
  --------------------------------- */

  function validateAgreement() {

    const agreeTerms =
      document.getElementById(
        'agreeTerms'
      );


    if (!agreeTerms?.checked) {

      showFormMessage(
        'Please agree to the Terms of Sale before saving the quotation.'
      );


      agreeTerms?.focus();

      return false;

    }


    return true;

  }


  /* --------------------------------
     CLEAR MESSAGE WHEN USER EDITS
  --------------------------------- */

  if (form) {

    form.addEventListener(
      'input',
      (event) => {

        if (
          event.target.matches(
            'input, select, textarea'
          )
        ) {

          clearFormMessage();

        }

      }
    );

  }


  /* --------------------------------
     FORM SUBMISSION
  --------------------------------- */

  form?.addEventListener(
    'submit',
    (event) => {

      /*
       * Stop accidental double submission.
       */

      if (isSubmitting) {

        event.preventDefault();

        return;

      }


      clearFormMessage();


      /*
       * Validate dates.
       */

      if (!validateDates()) {

        event.preventDefault();

        return;

      }


      /*
       * Validate states.
       */

      if (!validateStates()) {

        event.preventDefault();

        return;

      }


      /*
       * Validate items.
       */

      if (!validateItems()) {

        event.preventDefault();

        return;

      }


      /*
       * Validate customer.
       */

      if (!validateCustomer()) {

        event.preventDefault();

        return;

      }


      /*
       * Validate agreement.
       */

      if (!validateAgreement()) {

        event.preventDefault();

        return;

      }


      /*
       * Update total before submitting.
       */

      updateTotals();


      /*
       * Prevent duplicate submissions.
       */

      isSubmitting = true;


      if (submitButton) {

        submitButton.disabled =
          true;


        submitButton.dataset.originalText =
          submitButton.textContent.trim();


        submitButton.textContent =
          'Saving...';


        submitButton.style.opacity =
          '0.7';


        submitButton.style.cursor =
          'not-allowed';

      }


      showFormMessage(
        'Saving quotation...',
        true
      );


      /*
       * Do not use preventDefault()
       * here.
       *
       * Flask needs to receive
       * the POST request.
       */

    }
  );


  /* --------------------------------
     RESET BUTTON AFTER BACK/FORWARD
  --------------------------------- */

  window.addEventListener(
    'pageshow',
    () => {

      isSubmitting = false;


      if (submitButton) {

        submitButton.disabled =
          false;


        if (
          submitButton.dataset.originalText
        ) {

          submitButton.textContent =
            submitButton.dataset.originalText;

        }


        submitButton.style.opacity =
          '';


        submitButton.style.cursor =
          '';

      }

    }
  );

});