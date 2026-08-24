import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { DashboardLayout } from '../src/components/dashboard/DashboardLayout';
import { AuthProvider } from '../src/context/AuthContext';
import { NavigationProvider } from '../src/context/NavigationContext';
import { api } from '../src/services/api';

describe('BebshaX Dashboard Platform (Post-Sign-In Application)', () => {
  beforeEach(() => {
    api.setMockMode(true);
    window.history.pushState({}, '', '/create-study');
  });

  const renderDashboard = () => {
    return render(
      <NavigationProvider>
        <AuthProvider>
          <DashboardLayout />
        </AuthProvider>
      </NavigationProvider>
    );
  };

  it('renders brand sidebar, dynamic greeting, and New Study prompt hero', async () => {
    renderDashboard();

    expect(screen.getByText('BebshaX')).toBeInTheDocument();
    expect(screen.getByText(/Good (morning|afternoon|evening)/i)).toBeInTheDocument();
    expect(screen.getByText('What do you want to find out?')).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/Describe your business idea|Should we lead/i)
    ).toBeInTheDocument();
  });

  it('renders all 4 study type cards on New Study view', async () => {
    renderDashboard();

    expect(screen.getByText('User Interviews')).toBeInTheDocument();
    expect(screen.getByText('Concept & Demand')).toBeInTheDocument();
    expect(screen.getByText('Message Testing')).toBeInTheDocument();
    expect(screen.getByText('Pricing & WTP')).toBeInTheDocument();
  });

  it('navigates to Dashboard / Studies view showing BebshaX research hub banner and demo study', async () => {
    renderDashboard();

    // Click on Dashboard tab in sidebar
    const dashboardTab = screen.getByRole('button', { name: /Dashboard/i });
    fireEvent.click(dashboardTab);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^Studies$/i })).toBeInTheDocument();
      expect(screen.getByText('Synthetic Research Hub · Zero API Budget')).toBeInTheDocument();
      expect(screen.getByText('222 Free Routes')).toBeInTheDocument();
      expect(screen.getAllByText('Brand Messaging Discovery').length).toBeGreaterThan(0);
      expect(screen.getByText('DEMO STUDY')).toBeInTheDocument();
      expect(screen.getAllByText('Price Tracker Demand').length).toBeGreaterThan(0);
    });
  });

  it('navigates to Persona Library view showing empirical grounded personas', async () => {
    renderDashboard();

    // Click on Persona Library tab in sidebar
    const personaTab = screen.getByRole('button', { name: /Persona Library/i });
    fireEvent.click(personaTab);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^Persona Library$/i })).toBeInTheDocument();
      expect(screen.getByText('Saved personas and audiences you can reuse in any study.')).toBeInTheDocument();
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument();
    });
  });

  it('navigates to Model Router view showing FreeLLMpool active provider routes and telemetry', async () => {
    renderDashboard();

    // Click on Model Router tab in sidebar
    const routerTab = screen.getByRole('button', { name: /Model Router/i });
    fireEvent.click(routerTab);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Model Router & Telemetry/i })).toBeInTheDocument();
      expect(screen.getByText('Live Provider Health Matrix')).toBeInTheDocument();
      expect(screen.getByText('222 Free Model Routes')).toBeInTheDocument();
    });
  });

  it('initiates study workflow from New Study prompt and moves through steps', async () => {
    renderDashboard();

    const input = screen.getByPlaceholderText(/Describe your business idea|Should we lead/i);
    fireEvent.change(input, { target: { value: 'Test pricing sensitivity' } });

    const userInterviewsCard = screen.getByText('User Interviews');
    fireEvent.click(userInterviewsCard);

    await waitFor(() => {
      expect(screen.getByText('Design your user interviews')).toBeInTheDocument();
      expect(screen.getByText('Test pricing sensitivity')).toBeInTheDocument();
    });
  });

  it('renders research workflow directly when deep-linking to /research/tj6FY3cXDO8oxpuxeAMb/step1', async () => {
    window.history.pushState({}, '', '/research/tj6FY3cXDO8oxpuxeAMb/step1');
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Design your user interviews')).toBeInTheDocument();
      expect(screen.getByText('Context')).toBeInTheDocument();
      expect(screen.getByText('Personas')).toBeInTheDocument();
      expect(screen.getByText('Script')).toBeInTheDocument();
      expect(screen.getByText('Interviews')).toBeInTheDocument();
      expect(screen.getByText('Report')).toBeInTheDocument();
    });
  });

  it('renders persona library directly when deep-linking to /persona-library', async () => {
    window.history.pushState({}, '', '/persona-library');
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^Persona Library$/i })).toBeInTheDocument();
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument();
    });
  });
});
