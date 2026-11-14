import { Outlet, createBrowserRouter, RouterProvider } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import Layout from "./components/layout/Layout";
import { GuestOnly, RequireAuth, RequireCompany } from "./components/guards";
import Placeholder from "./pages/Placeholder";
import NotFound from "./pages/NotFound";
import Home from "./pages/Home";
import Opportunities from "./pages/Opportunities";
import OpportunityDetail from "./pages/OpportunityDetail";
import CompanyPublic from "./pages/CompanyPublic";
import Login from "./pages/auth/Login";
import Register from "./pages/auth/Register";
import ForgotPassword from "./pages/auth/ForgotPassword";
import ResetPassword from "./pages/auth/ResetPassword";
import VerifyEmail from "./pages/auth/VerifyEmail";
import Claim from "./pages/auth/Claim";
import AccountSecurity from "./pages/account/AccountSecurity";

/*
  Route map. Paths marked (fixed) are linked from the backend (emails,
  sitemap, QR codes) and must not change:
  /, /opportunities, /opportunities/:id, /companies/:slug, /companies/join,
  /companies/invite/:token, /company, /applications, /verify-email,
  /reset-password, /claim, /d/:code, /privacy.
*/
const page = (title) => <Placeholder title={title} />;

function Providers() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Outlet />
      </AuthProvider>
    </ThemeProvider>
  );
}

const router = createBrowserRouter([
  {
    element: <Providers />,
    children: [
      {
        element: <Layout />,
        children: [
          // Public
          { path: "/", element: <Home /> },
          { path: "/opportunities", element: <Opportunities /> },
          { path: "/opportunities/:id", element: <OpportunityDetail /> },
          { path: "/companies/join", element: page("Hire on SimplyFind") },
          { path: "/companies/invite/:token", element: page("Join your team") },
          { path: "/companies/:slug", element: <CompanyPublic /> },
          { path: "/d/:code", element: page("Recruitment drive") },
          { path: "/privacy", element: page("Privacy") },

          // Links from emails: work signed in or out
          { path: "/verify-email", element: <VerifyEmail /> },
          { path: "/reset-password", element: <ResetPassword /> },
          { path: "/claim", element: <Claim /> },

          // Signed out only
          {
            element: <GuestOnly />,
            children: [
              { path: "/login", element: <Login /> },
              { path: "/register", element: <Register /> },
              { path: "/forgot-password", element: <ForgotPassword /> },
            ],
          },

          // Signed in
          {
            element: <RequireAuth />,
            children: [
              { path: "/opportunities/:id/apply", element: page("Apply") },
              { path: "/profile/*", element: page("My profile") },
              { path: "/applications", element: page("My applications") },
              { path: "/saved", element: page("Saved roles") },
              { path: "/account/security", element: <AccountSecurity /> },
              {
                element: <RequireCompany />,
                children: [{ path: "/company/*", element: page("Company dashboard") }],
              },
            ],
          },

          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
