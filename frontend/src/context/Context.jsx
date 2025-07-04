import { createContext, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "react-toastify";

const Context = createContext();

const ContextProvider = (props) => {
  const backendUrl = import.meta.env.VITE_BACK_END_URL;
  const [token, settoken] = useState("");
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // Check if session has expired (3 days)
  const isSessionExpired = (loginTimestamp) => {
    const threeDaysInMs = 3 * 24 * 60 * 60 * 1000; // 3 days in milliseconds
    const currentTime = new Date().getTime();
    const loginTime = new Date(loginTimestamp).getTime();
    return (currentTime - loginTime) > threeDaysInMs;
  };

  useEffect(() => {
    const initializeAuth = async () => {
      const storedToken = localStorage.getItem("token");
      const loginTimestamp = localStorage.getItem("loginTimestamp");
      
      if (storedToken && loginTimestamp) {
        // Check if session has expired
        if (isSessionExpired(loginTimestamp)) {
          localStorage.removeItem("token");
          localStorage.removeItem("userId");
          localStorage.removeItem("loginTimestamp");
          settoken("");
          setUser(null);
          toast.error('Session expired. Please login again.');
          setLoading(false);
          return;
        }

        try {
          // Verify token with backend
          const response = await axios.get('http://localhost:4000/api/user/profile', {
            headers: {
              Authorization: `Bearer ${storedToken}`,
            },
          });
          settoken(storedToken);
          setUser(response.data.user);
        } catch (error) {
          console.error('Token validation failed:', error);
          localStorage.removeItem("token");
          localStorage.removeItem("userId");
          localStorage.removeItem("loginTimestamp");
          settoken("");
          setUser(null);
          toast.error('Session expired. Please login again.');
        }
      }
      setLoading(false);
    };

    initializeAuth();
  }, []);

  const login = (newToken, userData) => {
    const loginTime = new Date().toISOString();
    localStorage.setItem("token", newToken);
    localStorage.setItem("userId", userData._id);
    localStorage.setItem("loginTimestamp", loginTime);
    settoken(newToken);
    setUser(userData);
  };

  const logout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("userId");
    localStorage.removeItem("loginTimestamp");
    settoken("");
    setUser(null);
    toast.success('Logged out successfully');
  };

  const val = {
    backendUrl,
    token,
    settoken,
    user,
    setUser,
    login,
    logout,
    loading
  };

  return (
    <Context.Provider value={val}>{props.children}</Context.Provider>
  );
};

export { Context };
export default ContextProvider;