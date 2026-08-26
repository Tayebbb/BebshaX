export interface User {
  id: string;
  email: string;
  full_name: string;
  avatar_url?: string | null;
  is_active: boolean;
  is_verified: boolean;
  auth_provider: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in_days: number;
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
