import { User } from '../types/auth';

export const NEON_AUTH_URL =
  import.meta.env?.VITE_NEON_AUTH_URL ||
  'https://ep-cold-star-azazjakq.neonauth.c-3.ap-southeast-1.aws.neon.tech/neondb/auth';

export interface NeonAuthUser {
  id: string;
  name: string;
  email: string;
  emailVerified: boolean;
  image?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NeonAuthResponse {
  user: User;
  token?: string | null;
  emailVerificationRequired?: boolean;
}

function mapNeonUserToAppUser(neonUser: NeonAuthUser): User {
  return {
    id: neonUser.id,
    email: neonUser.email,
    full_name: neonUser.name || neonUser.email.split('@')[0],
    avatar_url: neonUser.image || null,
    is_active: true,
    is_verified: !!neonUser.emailVerified,
    auth_provider: 'neon',
    created_at: neonUser.createdAt || new Date().toISOString(),
  };
}

export const neonAuth = {
  getAuthUrl(): string {
    return NEON_AUTH_URL;
  },

  async signUp(params: {
    email: string;
    password: string;
    name: string;
  }): Promise<NeonAuthResponse> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    const res = await fetch(`${NEON_AUTH_URL}/sign-up/email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
      },
      credentials: 'include',
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        password: params.password,
        name: params.name.trim(),
        callbackURL: origin,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (data.code === 'USER_ALREADY_EXISTS') {
        throw new Error('An account with this email address already exists.');
      }
      if (data.code === 'PASSWORD_TOO_SHORT') {
        throw new Error('Password must be at least 8 characters long.');
      }
      throw new Error(data.message || 'Registration failed. Please check your credentials.');
    }

    const appUser = mapNeonUserToAppUser(data.user);
    return {
      user: appUser,
      token: data.token || null,
      emailVerificationRequired: !data.user.emailVerified,
    };
  },

  async signIn(params: {
    email: string;
    password: string;
  }): Promise<NeonAuthResponse> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    const res = await fetch(`${NEON_AUTH_URL}/sign-in/email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
      },
      credentials: 'include',
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        password: params.password,
        callbackURL: origin,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (data.code === 'EMAIL_NOT_VERIFIED') {
        const err = new Error(
          'Email not verified. Please check your email inbox for the verification link.'
        ) as Error & { code: string; email: string };
        err.code = 'EMAIL_NOT_VERIFIED';
        err.email = params.email;
        throw err;
      }
      if (data.code === 'INVALID_EMAIL_OR_PASSWORD') {
        throw new Error('Invalid email or password.');
      }
      throw new Error(data.message || 'Invalid email or password.');
    }

    const appUser = mapNeonUserToAppUser(data.user);
    return {
      user: appUser,
      token: data.token || null,
    };
  },

  async signInWithGoogle(): Promise<void> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    const res = await fetch(`${NEON_AUTH_URL}/sign-in/social`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
      },
      credentials: 'include',
      body: JSON.stringify({
        provider: 'google',
        callbackURL: origin,
      }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.message || 'Google sign-in initialization failed.');
    }

    const data = await res.json();
    if (data.url && typeof window !== 'undefined') {
      window.location.href = data.url;
    }
  },

  async sendVerificationEmail(email: string): Promise<boolean> {
    return this.sendVerificationOtp(email, 'email-verification');
  },

  async sendVerificationOtp(
    email: string,
    type: 'email-verification' | 'forget-password' | 'sign-in' = 'email-verification'
  ): Promise<boolean> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    try {
      const res = await fetch(`${NEON_AUTH_URL}/email-otp/send-verification-otp`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Origin: origin,
        },
        body: JSON.stringify({
          email: email.trim().toLowerCase(),
          type,
        }),
      });
      return res.ok;
    } catch {
      return false;
    }
  },

  async verifyEmailOtp(params: { email: string; otp: string }): Promise<NeonAuthResponse> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    const res = await fetch(`${NEON_AUTH_URL}/email-otp/verify-email`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
      },
      credentials: 'include',
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        otp: params.otp.trim(),
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (data.code === 'INVALID_OTP') {
        throw new Error('Invalid verification code. Please check and try again.');
      }
      if (data.code === 'OTP_EXPIRED') {
        throw new Error('Verification code has expired. Please click "Resend code".');
      }
      throw new Error(data.message || 'Verification failed. Please try again.');
    }

    const appUser = data.user
      ? mapNeonUserToAppUser(data.user)
      : {
          id: `usr_${Date.now()}`,
          email: params.email.trim().toLowerCase(),
          full_name: params.email.split('@')[0],
          avatar_url: null,
          is_active: true,
          is_verified: true,
          auth_provider: 'neon',
          created_at: new Date().toISOString(),
        };

    return {
      user: appUser,
      token: data.token || null,
      emailVerificationRequired: false,
    };
  },

  async resetPasswordWithOtp(params: {
    email: string;
    otp: string;
    password: string;
  }): Promise<boolean> {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:5173';
    const res = await fetch(`${NEON_AUTH_URL}/email-otp/reset-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Origin: origin,
      },
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        otp: params.otp.trim(),
        password: params.password,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (data.code === 'INVALID_OTP') {
        throw new Error('Invalid reset code. Please check and try again.');
      }
      if (data.code === 'OTP_EXPIRED') {
        throw new Error('Reset code has expired. Please request a new one.');
      }
      if (data.code === 'PASSWORD_TOO_SHORT') {
        throw new Error('New password must be at least 8 characters long.');
      }
      throw new Error(data.message || 'Password reset failed.');
    }

    return true;
  },

  async getSession(token?: string | null): Promise<User | null> {
    try {
      const headers: Record<string, string> = {};
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      const res = await fetch(`${NEON_AUTH_URL}/get-session`, {
        method: 'GET',
        headers,
        credentials: 'include',
        signal: AbortSignal.timeout(4000),
      });

      if (res.ok) {
        const data = await res.json();
        if (data?.user) {
          return mapNeonUserToAppUser(data.user);
        }
      }
    } catch {
      // ignore network/offline errors
    }
    return null;
  },

  async signOut(): Promise<void> {
    try {
      await fetch(`${NEON_AUTH_URL}/sign-out`, {
        method: 'POST',
        credentials: 'include',
        signal: AbortSignal.timeout(3000),
      });
    } catch {
      // ignore
    }
  },
};
