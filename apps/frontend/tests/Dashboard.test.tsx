import { describe, it, expect, beforeEach, vi } from 'vitest';
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

  it('navigates to Dashboard / Studies view showing studies and demo study', async () => {
    renderDashboard();

    // Click on Dashboard tab in sidebar
    const dashboardTab = screen.getByRole('button', { name: /Dashboard/i });
    fireEvent.click(dashboardTab);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^Studies$/i })).toBeInTheDocument();
      expect(screen.getAllByText('Brand Messaging Discovery').length).toBeGreaterThan(0);
      expect(screen.getByText('DEMO STUDY')).toBeInTheDocument();
      expect(screen.getAllByText('Price Tracker Demand').length).toBeGreaterThan(0);
    });
  });

  it('navigates to Persona Library showing saved personas with a synthetic research disclosure', async () => {
    renderDashboard();

    // Click on Persona Library tab in sidebar
    const personaTab = screen.getByRole('button', { name: /Persona Library/i });
    fireEvent.click(personaTab);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^Persona Library$/i })).toBeInTheDocument();
      expect(screen.getByText('Synthetic participants: findings are research hypotheses to validate with real users.')).toBeVisible();
      expect(screen.getByText('Sarah Chen')).toBeInTheDocument();
    });
  });

  it('keeps loaded recent study links visible while navigation refresh is pending', async () => {
    const getStudies = vi.spyOn(api, 'getStudies');
    try {
      renderDashboard();

      expect(await screen.findByRole('button', { name: 'Brand Messaging Discovery' })).toBeVisible();
      expect(screen.getByRole('button', { name: 'Price Tracker Demand' })).toBeVisible();

      getStudies.mockImplementation(() => new Promise(() => {}));
      const callsBeforeNavigation = getStudies.mock.calls.length;
      fireEvent.click(screen.getByRole('button', { name: /Persona Library/i }));

      await waitFor(() => {
        expect(getStudies.mock.calls.length).toBeGreaterThan(callsBeforeNavigation);
        expect(screen.getByRole('heading', { name: /^Persona Library$/i })).toBeInTheDocument();
      });
      expect(screen.getByRole('button', { name: 'Brand Messaging Discovery' })).toBeVisible();
      expect(screen.getByRole('button', { name: 'Price Tracker Demand' })).toBeVisible();
    } finally {
      getStudies.mockRestore();
    }
  });

  it('renders primary sidebar navigation tabs without Model Router', async () => {
    renderDashboard();

    expect(screen.getByRole('button', { name: /New Study/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Persona Library/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Model Router/i })).toBeNull();
  });

  it('starts the selected study workflow only after explicit submission', async () => {
    renderDashboard();

    const input = screen.getByPlaceholderText(/Describe your business idea|Should we lead/i);
    fireEvent.change(input, { target: { value: 'Test pricing sensitivity' } });

    const userInterviewsCard = screen.getByText('User Interviews');
    fireEvent.click(userInterviewsCard);

    expect(screen.getByRole('heading', { name: 'What do you want to find out?' })).toBeInTheDocument();
    expect(screen.queryByText('Design your user interviews')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Start research study' }));

    await waitFor(() => {
      expect(screen.getByText('Design your user interviews')).toBeInTheDocument();
      expect(screen.getByText('Test pricing sensitivity')).toBeInTheDocument();
    });
  });

  it('renders research workflow directly when deep-linking to /research/tj6FY3cXDO8oxpuxeAMb/step1', async () => {
    await api.createStudy({ id: 'tj6FY3cXDO8oxpuxeAMb', title: 'Deep-linked study', type: 'interviews' });
    window.history.pushState({}, '', '/research/tj6FY3cXDO8oxpuxeAMb/step1');
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText('Design your user interviews')).toBeInTheDocument();
      expect(screen.getByText('Context')).toBeInTheDocument();
      expect(screen.getByText('Personas')).toBeInTheDocument();
      expect(screen.getByText('Script')).toBeInTheDocument();
      expect(screen.getAllByText('Interviews').length).toBeGreaterThanOrEqual(1);
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
