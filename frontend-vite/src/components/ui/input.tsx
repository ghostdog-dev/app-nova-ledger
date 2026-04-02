import { InputHTMLAttributes, forwardRef, useId } from 'react';
import { clsx } from 'clsx';
import styles from './input.module.css';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, leftIcon, rightIcon, className, id, ...props }, ref) => {
    const generatedId = useId();
    const inputId = id ?? generatedId;
    const errorId = `${inputId}-error`;
    const hintId = `${inputId}-hint`;

    return (
      <div className={styles.wrapper}>
        {label && (
          <label
            htmlFor={inputId}
            className={styles.label}
          >
            {label}
            {props.required && (
              <span className={styles.required} aria-hidden="true">
                *
              </span>
            )}
          </label>
        )}
        <div className={styles.inputWrapper}>
          {leftIcon && (
            <div className={styles.leftIcon}>
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={clsx(
              styles.input,
              error && styles.inputError,
              leftIcon && styles.inputWithLeftIcon,
              rightIcon && styles.inputWithRightIcon,
              className
            )}
            aria-invalid={error ? 'true' : undefined}
            aria-describedby={
              [error && errorId, hint && hintId].filter(Boolean).join(' ') || undefined
            }
            {...props}
          />
          {rightIcon && (
            <div className={styles.rightIcon}>
              {rightIcon}
            </div>
          )}
        </div>
        {hint && !error && (
          <p id={hintId} className={styles.hint}>
            {hint}
          </p>
        )}
        {error && (
          <p id={errorId} className={styles.error} role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
