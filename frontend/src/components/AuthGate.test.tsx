import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";

describe("AuthGate", () => {
  it("defaults to login mode and calls onLogin, not onSignup, on submit", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    const onSignup = vi.fn().mockResolvedValue(undefined);
    render(<AuthGate onLogin={onLogin} onSignup={onSignup} error={null} />);

    await user.type(screen.getByPlaceholderText("Email"), "sam@example.com");
    await user.type(screen.getByPlaceholderText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(onLogin).toHaveBeenCalledWith("sam@example.com", "correct-horse-battery");
    expect(onSignup).not.toHaveBeenCalled();
  });

  it("switches to signup mode and calls onSignup, not onLogin", async () => {
    const user = userEvent.setup();
    const onLogin = vi.fn().mockResolvedValue(undefined);
    const onSignup = vi.fn().mockResolvedValue(undefined);
    render(<AuthGate onLogin={onLogin} onSignup={onSignup} error={null} />);

    await user.click(screen.getByText(/New here\? Create an account/));
    await user.type(screen.getByPlaceholderText("Email"), "new@example.com");
    await user.type(screen.getByPlaceholderText("Password"), "another-password");
    await user.click(screen.getByRole("button", { name: "Sign up" }));

    expect(onSignup).toHaveBeenCalledWith("new@example.com", "another-password");
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("toggles back to login mode when clicked twice", async () => {
    const user = userEvent.setup();
    render(<AuthGate onLogin={vi.fn()} onSignup={vi.fn()} error={null} />);
    await user.click(screen.getByText(/New here\? Create an account/));
    expect(screen.getByRole("button", { name: "Sign up" })).toBeInTheDocument();
    await user.click(screen.getByText(/Already have an account\? Sign in/));
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("displays the error message when provided", () => {
    render(<AuthGate onLogin={vi.fn()} onSignup={vi.fn()} error="Incorrect email or password" />);
    expect(screen.getByText("Incorrect email or password")).toBeInTheDocument();
  });

  it("enforces an 8-character minimum on the password field", () => {
    render(<AuthGate onLogin={vi.fn()} onSignup={vi.fn()} error={null} />);
    const password = screen.getByPlaceholderText("Password") as HTMLInputElement;
    expect(password.minLength).toBe(8);
  });
});
