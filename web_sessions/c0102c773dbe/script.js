(function () {
  'use strict';

  const display = document.getElementById('display');

  let currentOperand = '';
  let previousOperand = '';
  let operation = null;
  let shouldResetDisplay = false;

  function updateDisplay(value) {
    display.textContent = value;
  }

  function clearAll() {
    currentOperand = '';
    previousOperand = '';
    operation = null;
    shouldResetDisplay = false;
    updateDisplay('0');
  }

  function appendNumber(number) {
    if (shouldResetDisplay) {
      currentOperand = '';
      shouldResetDisplay = false;
    }
    // Prevent multiple leading zeros
    if (currentOperand === '0' && number === '0') return;
    if (currentOperand === '0' && number !== '0') {
      currentOperand = number;
    } else {
      currentOperand += number;
    }
    updateDisplay(currentOperand);
  }

  function chooseOperation(op) {
    if (currentOperand === '' && previousOperand === '') return;

    if (currentOperand === '' && previousOperand !== '') {
      // User is changing the operation
      operation = op;
      return;
    }

    if (previousOperand !== '' && currentOperand !== '') {
      compute();
    }

    operation = op;
    previousOperand = currentOperand;
    currentOperand = '';
    shouldResetDisplay = false;
  }

  function compute() {
    if (operation === null || previousOperand === '') return;
    if (currentOperand === '' && shouldResetDisplay) {
      // Re-apply the same operation with the last result
      // Already handled by equals logic
      return;
    }

    const prev = parseFloat(previousOperand);
    const curr = parseFloat(currentOperand || '0');

    if (isNaN(prev) || isNaN(curr)) return;

    let result;
    switch (operation) {
      case '+':
        result = prev + curr;
        break;
      case '-':
        result = prev - curr;
        break;
      case '*':
        result = prev * curr;
        break;
      case '/':
        if (curr === 0) {
          clearAll();
          updateDisplay('Error');
          return;
        }
        result = prev / curr;
        break;
      default:
        return;
    }

    // Round to avoid floating-point issues
    result = Math.round((result + Number.EPSILON) * 100000000) / 100000000;

    currentOperand = result.toString();
    operation = null;
    previousOperand = '';
    shouldResetDisplay = true;
    updateDisplay(currentOperand);
  }

  function handleButtonClick(e) {
    const btn = e.target.closest('button');
    if (!btn) return;

    const id = btn.id;

    if (id === 'btn-clear') {
      clearAll();
    } else if (id === 'btn-equals') {
      compute();
    } else if (id === 'btn-add') {
      chooseOperation('+');
    } else if (id === 'btn-subtract') {
      chooseOperation('-');
    } else if (id === 'btn-multiply') {
      chooseOperation('*');
    } else if (id === 'btn-divide') {
      chooseOperation('/');
    } else {
      // Number buttons: btn-0 through btn-9
      const match = id.match(/^btn-(\d)$/);
      if (match) {
        appendNumber(match[1]);
      }
    }
  }

  document.querySelector('.buttons').addEventListener('click', handleButtonClick);

  // Keyboard support
  document.addEventListener('keydown', function (e) {
    const key = e.key;
    if (key >= '0' && key <= '9') {
      appendNumber(key);
    } else if (key === '+') {
      chooseOperation('+');
    } else if (key === '-') {
      chooseOperation('-');
    } else if (key === '*') {
      chooseOperation('*');
    } else if (key === '/') {
      e.preventDefault();
      chooseOperation('/');
    } else if (key === 'Enter' || key === '=') {
      e.preventDefault();
      compute();
    } else if (key === 'Escape' || key === 'c' || key === 'C') {
      clearAll();
    }
  });

  // Initialize display
  updateDisplay('0');
})();
