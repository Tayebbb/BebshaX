export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  is_verified: boolean;
  auth_provider: string;
  /** Server-verified role; gates developer-only diagnostics in the UI. */
  role?: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in_days: number;
  expires_in?: number;
  refresh_token?: string | null;
  session_id?: string | null;
  session_expires_at?: string | null;
  csrf_token?: string | null;
  verification_required?: boolean;
  user: User;
}

export interface SignInData {
  email: string;
  password: string;
}

export interface SignUpData {
  full_name: string;
  email: string;
  password: string;
}

export interface GoogleAuthData {
  credential?: string;
  email?: string;
  name?: string;
  avatar_url?: string;
}
