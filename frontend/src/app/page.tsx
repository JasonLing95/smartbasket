// src/app/page.tsx
"use client";

import React, { useEffect, useState, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, ArrowRight, TrendingDown, Loader2, Search, Plus, Minus, Trash2, ShoppingBasket, HelpCircle, Receipt, Lock, User, Mail, Sparkles, Check, ChevronDown, LogOut, Camera, ChevronRight, X, Info, Zap, ChevronUp } from "lucide-react";
import SmartBasketPlusModal from '@/components/SmartBasketPlusModal';

// --- Types ---
interface DetailedBasketItem { id: string; name: string; quantity: number; }
interface BasketOption { store_name: string; total_cost: number; items_counted: number; items_detailed?: DetailedBasketItem[]; }
interface PriceAlert { item_name: string; current_store: string; cheaper_store: string; old_price: number; new_price: number; potential_savings: number; }
interface CatalogItem { id: string; canonical_name: string; category: string; variant_count?: number; }
interface BasketItemPrice { price: number; confidence: number; }
interface BasketItem { id: string; name: string; category: string; quantity: number; prices: Record<string, BasketItemPrice | null>; }
interface ReceiptHistoryItem { id: string; store_name: string; total_spent: number; date: string; items_count: number; }

interface ReceiptDetails {
  store_name: string;
  total_spent: number;
  date: string;
  items: { name: string; category: string; price: number }[];
}

export default function Page() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "catalog">("dashboard");
  const [isPremiumModalOpen, setIsPremiumModalOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [showAdvancedInsights, setShowAdvancedInsights] = useState(false);

  // Auth States
  const [token, setToken] = useState<string | null>(null);
  const [activeUser, setActiveUser] = useState<string | null>(null);
  const [isAuthRegister, setIsAuthRegister] = useState<boolean>(false);
  const [authUsername, setAuthUsername] = useState("");
  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [authModalError, setAuthModalError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{username?: string, email?: string, password?: string}>({});
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [pendingAddItem, setPendingAddItem] = useState<string | null>(null);

  // App States
  const [basketOptions, setBasketOptions] = useState<BasketOption[]>([]);
  const [basketItems, setBasketItems] = useState<BasketItem[]>([]);
  const [availableStores, setAvailableStores] = useState<string[]>(["Aldi", "Tesco"]);
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [catalogItems, setCatalogItems] = useState<CatalogItem[]>([]);
  const [catalogPage, setCatalogPage] = useState<number>(1);
  const [totalCatalogPages, setTotalCatalogPages] = useState<number>(1);
  const [expandedItemId, setExpandedItemId] = useState<string | null>(null);
  const [itemVariants, setItemVariants] = useState<any[]>([]);
  const [loadingVariants, setLoadingVariants] = useState<boolean>(false);
  const [viewReceipt, setViewReceipt] = useState<ReceiptDetails | null>(null);
  const [loadingReceipt, setLoadingReceipt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<CatalogItem[]>([]);
  const [actionId, setActionId] = useState<string | null>(null);
  const [receiptsHistory, setReceiptsHistory] = useState<ReceiptHistoryItem[]>([]);
  const [optimizedSplit, setOptimizedSplit] = useState<any>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const carouselRef = useRef<HTMLDivElement>(null);
  const [isCarouselPaused, setIsCarouselPaused] = useState(false);
  const [liveDropAlert, setLiveDropAlert] = useState<string | null>(null);

  const [toastNotice, setToastNotice] = useState<{ text: string; type: "success" | "cached" | "error" | "info" } | null>(null);
  const toastTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  const showToast = (text: string, type: "success" | "cached" | "error" | "info") => {
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    setToastNotice({ text, type });
    toastTimeoutRef.current = setTimeout(() => setToastNotice(null), 4500);
  };

  useEffect(() => {
    const cachedToken = localStorage.getItem("sb_token");
    const cachedUser = localStorage.getItem("sb_username");
    if (cachedToken && cachedUser) { setToken(cachedToken); setActiveUser(cachedUser); }
  }, []);

  useEffect(() => {
    if (isCarouselPaused || alerts.length < 4) return;
    const container = carouselRef.current;
    if (!container) return;

    let animationId: number;

    const scroll = () => {
      if (container) {
        container.scrollLeft += 1; 
        const halfwayPoint = container.scrollWidth / 2;
        const hitRightWall = Math.ceil(container.scrollLeft + container.clientWidth) >= container.scrollWidth;
        if (container.scrollLeft >= halfwayPoint || hitRightWall) {
          container.scrollLeft = 0;
        }
      }
      animationId = requestAnimationFrame(scroll);
    };

    animationId = requestAnimationFrame(scroll);
    return () => cancelAnimationFrame(animationId);
  }, [isCarouselPaused, alerts.length]);

  useEffect(() => {
    if (!activeUser) return;
    const eventSource = new EventSource(`${API_BASE}/api/stream/alerts?username=${encodeURIComponent(activeUser)}`);
    eventSource.onmessage = (event) => {
      setLiveDropAlert(event.data);
      refreshDashboardMetrics();
    };
    return () => { eventSource.close(); };
  }, [activeUser, API_BASE]);

  async function refreshDashboardMetrics() {
    try {
      const fetchHeaders: HeadersInit = token ? { "Authorization": `Bearer ${token}` } : {};
      const alertsRes = await fetch(`${API_BASE}/api/alerts`, { headers: fetchHeaders });
      if (alertsRes.ok) {
        const alertsData = await alertsRes.json();
        setAlerts(alertsData.active_alerts || []);
      }

      if (token) {
        const [basketRes, itemsRes, receiptsRes] = await Promise.all([
          fetch(`${API_BASE}/api/basket/compare?friction_penalty=0`, { headers: fetchHeaders }),
          fetch(`${API_BASE}/api/basket/items`, { headers: fetchHeaders }),
          fetch(`${API_BASE}/api/receipts`, { headers: fetchHeaders })
        ]);

        if (basketRes.status === 401) { handleLogout(); return; }
        const basketData = await basketRes.json();
        const itemsData = await itemsRes.json();
        const receiptsData = await receiptsRes.json();

        if (basketData.basket_options) setBasketOptions(basketData.basket_options);
        if (basketData.optimized_split) setOptimizedSplit(basketData.optimized_split);
        if (itemsData.items) setBasketItems(itemsData.items);
        if (itemsData.stores) setAvailableStores(itemsData.stores);
        if (receiptsData.receipts) setReceiptsHistory(receiptsData.receipts);
      }
    } catch (error) {
      showToast("Connection failed. Please refresh.", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refreshDashboardMetrics(); }, [API_BASE, token]);

  useEffect(() => {
    if (activeTab === "catalog" && searchQuery.trim().length < 2) {
      fetch(`${API_BASE}/api/catalog/all?page=${catalogPage}&limit=10`)
        .then(res => res.json())
        .then(data => { setCatalogItems(data.results || []); setTotalCatalogPages(data.total_pages || 1); })
        .catch(() => showToast("Failed to load items.", "error"));
    }
  }, [activeTab, catalogPage, searchQuery, API_BASE]);

  useEffect(() => {
    async function executeSearch() {
      if (searchQuery.trim().length < 2) { setSearchResults([]); return; }
      try {
        const res = await fetch(`${API_BASE}/api/catalog/search?q=${encodeURIComponent(searchQuery)}`);
        const data = await res.json();
        if (data.results) setSearchResults(data.results);
      } catch (err) {}
    }
    const delayDebounceFn = setTimeout(() => executeSearch(), 250);
    return () => clearTimeout(delayDebounceFn);
  }, [searchQuery, API_BASE]);

  async function handleRowToggle(itemId: string) {
    if (expandedItemId === itemId) { setExpandedItemId(null); setItemVariants([]); return; }
    setExpandedItemId(itemId); setLoadingVariants(true); setItemVariants([]);
    try {
      const res = await fetch(`${API_BASE}/api/catalog/item/${itemId}/variants`);
      if (res.ok) { const data = await res.json(); setItemVariants(data.variants || []); }
    } catch (err) { showToast("Could not load store prices.", "error"); } 
    finally { setLoadingVariants(false); }
  }

  async function handleAuthSubmission(e: React.FormEvent) {
    e.preventDefault(); setAuthModalError(null);
    const errors: any = {};
    if (!authUsername.trim()) errors.username = "Username is required";
    if (isAuthRegister && !authEmail.trim()) errors.email = "Email is required";
    if (isAuthRegister && authEmail.trim() && !authEmail.includes("@")) errors.email = "Valid email required";
    if (!authPassword) errors.password = "Password is required";
    if (Object.keys(errors).length > 0) { setFieldErrors(errors); return; }
    
    setFieldErrors({}); setAuthLoading(true);
    const endpoint = isAuthRegister ? "/api/auth/register" : "/api/auth/login";
    try {
      const response = await fetch(`${API_BASE}${endpoint}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: authUsername, email: authEmail, password: authPassword }) });
      const data = await response.json();

      if (!response.ok) {
        if (!isAuthRegister && response.status === 404 && data.detail === "User not found.") { setIsAuthRegister(true); setFieldErrors({}); setAuthModalError("No account found! Directing to sign up..."); }
        else if (response.status === 401 && data.detail === "Invalid password.") setFieldErrors({ password: "Incorrect password." });
        else setAuthModalError(data.detail || "Something went wrong.");
      } else {
        localStorage.setItem("sb_token", data.token); localStorage.setItem("sb_username", data.username);
        setToken(data.token); setActiveUser(data.username); setShowAuthModal(false); setAuthEmail(""); setAuthPassword("");
        if (pendingAddItem) {
          setActionId(pendingAddItem);
          await fetch(`${API_BASE}/api/basket/add`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${data.token}` }, body: JSON.stringify({ master_item_id: pendingAddItem, quantity: 1 }) });
          setPendingAddItem(null); setActionId(null);
        }
        showToast(`Welcome, ${data.username}!`, "success");
      }
    } catch (err) { setAuthModalError("Network error."); } finally { setAuthLoading(false); }
  }

  function handleLogout() {
    fetch(`${API_BASE}/api/auth/logout`, { method: "POST", headers: { "Authorization": `Bearer ${token}` } }).catch(() => {});
    localStorage.removeItem("sb_token"); localStorage.removeItem("sb_username");
    setToken(null); setActiveUser(null); setBasketItems([]); setBasketOptions([]); setOptimizedSplit(null); setReceiptsHistory([]); setIsProfileMenuOpen(false);
  }

  async function handleAddItem(masterItemId: string) {
    if (!token) { setPendingAddItem(masterItemId); setShowAuthModal(true); return; }
    try {
      setActionId(masterItemId);
      const response = await fetch(`${API_BASE}/api/basket/add`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` }, body: JSON.stringify({ master_item_id: masterItemId, quantity: 1 }) });
      if (response.ok) await refreshDashboardMetrics();
    } catch (err) { showToast("Couldn't add item.", "error"); } finally { setActionId(null); }
  }

  async function handleModifyQuantity(masterItemId: string, currentQty: number, action: "increment" | "decrement" | "delete") {
    const trueAction = (action === "decrement" && currentQty <= 1) ? "delete" : action;
    try {
      setActionId(`${masterItemId}-${action}`);
      const response = await fetch(`${API_BASE}/api/basket/update`, { method: "POST", headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` }, body: JSON.stringify({ master_item_id: masterItemId, action: trueAction }) });
      if (response.ok) await refreshDashboardMetrics();
    } catch (err) { showToast("Couldn't update basket.", "error"); } finally { setActionId(null); }
  }

  const handleReceiptUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    setUploading(true);
    const formData = new FormData(); formData.append("file", e.target.files[0]);
    try {
      const headers: HeadersInit = token ? { "Authorization": `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE}/api/receipts/upload`, { method: "POST", headers, body: formData });
      const data = await res.json();
      if (!res.ok) showToast(data.detail || "Couldn't read the receipt.", "error");
      else if (data.cached) showToast("Duplicate receipt.", "cached");
      else showToast(`Scanned items from ${data.store_detected || "receipt"}.`, "success");
      await refreshDashboardMetrics();
    } catch (error) { showToast("Upload failed.", "error"); } finally { setUploading(false); e.target.value = ""; }
  };

  const getCheapestPrice = (prices: Record<string, BasketItemPrice | null>) => {
    let minPrice = Infinity; let bestStore = "";
    Object.entries(prices).forEach(([store, data]) => {
      if (data && data.price < minPrice) { minPrice = data.price; bestStore = store; }
    });
    return { minPrice: minPrice === Infinity ? null : minPrice, bestStore };
  };

  async function handleViewReceipt(id: string) {
    setLoadingReceipt(id);
    try {
      const fetchHeaders: HeadersInit = token ? { "Authorization": `Bearer ${token}` } : {};
      const res = await fetch(`${API_BASE}/api/receipts/${id}`, { headers: fetchHeaders });
      if (res.ok) {
        const data = await res.json();
        setViewReceipt(data);
      } else {
        showToast("Couldn't load that receipt. Please try again.", "error");
      }
    } catch (e) {
      showToast("Network error loading receipt.", "error");
    } finally {
      setLoadingReceipt(null);
    }
  }

  if (loading)
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#F9FAFB] space-y-4">
        <Loader2 className="w-6 h-6 text-emerald-600 animate-spin" />
      </div>
    );

  const displayedCatalogItems = searchQuery.trim().length >= 2 ? searchResults : catalogItems;

  return (
    <main className="min-h-screen w-full bg-[#F9FAFB] font-sans text-slate-900 pb-24 selection:bg-emerald-100 selection:text-emerald-900">
      
      {/* 1. MINIMAL NAVIGATION */}
      <nav className="sticky top-0 z-40 bg-[#F9FAFB]/80 backdrop-blur-xl border-b border-slate-200/50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-xl bg-slate-900 flex items-center justify-center shadow-sm">
                <ShoppingBasket className="w-4 h-4 text-white" />
              </div>
              <span className="font-bold tracking-tight text-lg hidden sm:block">SmartBasket</span>
            </div>
            
            <div className="flex items-center gap-1 bg-slate-200/40 p-1 rounded-full">
              <button onClick={() => setActiveTab("dashboard")} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === "dashboard" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"}`}>Home</button>
              <button onClick={() => setActiveTab("catalog")} className={`px-4 py-1.5 rounded-full text-sm font-medium transition-all ${activeTab === "catalog" ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"}`}>Browse Items</button>
            </div>
          </div>

          <div className="flex items-center gap-3 relative">
            <button onClick={() => setIsPremiumModalOpen(true)} className="hidden md:flex items-center gap-1.5 bg-amber-50 text-amber-600 hover:bg-amber-100 px-3 py-1.5 rounded-full text-xs font-bold transition-colors">
              <Sparkles className="w-3.5 h-3.5" /> Upgrade
            </button>
            
            {token ? (
              <div>
                <button onClick={() => setIsProfileMenuOpen(!isProfileMenuOpen)} className="flex items-center gap-2 hover:bg-slate-100 p-1.5 pr-3 rounded-full transition-colors">
                  <div className="w-7 h-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-xs">{activeUser?.charAt(0).toUpperCase()}</div>
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                </button>
                {isProfileMenuOpen && (
                  <div className="absolute right-0 top-12 w-48 bg-white rounded-2xl shadow-xl border border-slate-100 py-2 z-50 animate-in fade-in slide-in-from-top-2">
                    <div className="px-4 py-2 border-b border-slate-50 mb-2">
                      <p className="text-sm font-semibold truncate">{activeUser}</p>
                    </div>
                    <button onClick={() => setIsPremiumModalOpen(true)} className="w-full text-left px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 hover:text-amber-600 flex items-center gap-2">
                      <Sparkles className="w-4 h-4" /> SmartBasket+
                    </button>
                    <button onClick={handleLogout} className="w-full text-left px-4 py-2 text-sm text-slate-600 hover:bg-rose-50 hover:text-rose-600 flex items-center gap-2">
                      <LogOut className="w-4 h-4" /> Sign Out
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <Button onClick={() => setShowAuthModal(true)} className="bg-slate-900 text-white rounded-full px-5 font-semibold text-sm">Sign In</Button>
            )}
          </div>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-8 space-y-12">
        
        {/* COMPACT PRICE ALERTS (CAROUSEL) */}
        <section className="relative">
          <div className="flex items-center gap-2 mb-3 px-1">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <h2 className="text-sm font-bold text-slate-600 uppercase tracking-wider">
              {token ? "Today's Best Deals" : "Community Deals"}
            </h2>
          </div>
          
          {alerts.length > 0 ? (
            <>
              <div 
                ref={carouselRef} 
                onMouseEnter={() => setIsCarouselPaused(true)} 
                onMouseLeave={() => setIsCarouselPaused(false)} 
                onTouchStart={() => setIsCarouselPaused(true)} 
                onTouchEnd={() => setIsCarouselPaused(false)} 
                className={`flex gap-3 pb-4 [&::-webkit-scrollbar]:hidden ${alerts.length >= 4 ? 'overflow-x-hidden' : 'overflow-x-auto'}`}
              >
                {(alerts.length >= 4 ? [...alerts, ...alerts] : alerts).map((alert, index) => (
                  <div 
                    key={index} 
                    className="shrink-0 w-[260px] bg-white border border-slate-200/60 rounded-2xl p-4 shadow-sm flex flex-col gap-1"
                  >
                    <p className="font-semibold text-slate-900 text-sm truncate">{alert.item_name}</p>
                    <div className="text-sm font-bold text-emerald-600 flex items-center gap-1 mt-1">
                      Save £{alert.potential_savings.toFixed(2)}
                      <span className="text-xs text-slate-500 font-medium ml-1">at {alert.cheaper_store}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="absolute right-0 top-8 bottom-4 w-12 bg-gradient-to-l from-[#F9FAFB] to-transparent pointer-events-none z-10" />
            </>
          ) : (
            <div className="bg-white border border-slate-200/60 border-dashed rounded-3xl p-6 text-center shadow-sm max-w-2xl">
              {token ? (
                basketItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center space-y-3">
                    <div className="w-10 h-10 bg-emerald-50 rounded-full flex items-center justify-center">
                      <Sparkles className="w-5 h-5 text-emerald-500" />
                    </div>
                    <h3 className="text-sm font-bold text-slate-800">Start Saving Money</h3>
                    <p className="text-xs text-slate-500 max-w-sm mx-auto">
                      Add some items to your basket and we'll help you find the cheapest places to shop.
                    </p>
                    <Button 
                      size="sm" 
                      onClick={() => setActiveTab("catalog")} 
                      className="bg-slate-900 hover:bg-slate-800 text-white rounded-full font-semibold px-6 mt-2"
                    >
                      Browse Items
                    </Button>
                  </div>
                ) : (
                  <div className="py-4">
                    <p className="text-sm font-bold text-slate-700">You're getting the best possible prices!</p>
                    <p className="text-xs text-slate-500 mt-1">Check back later for more deals.</p>
                  </div>
                )
              ) : (
                <div className="py-4">
                  <p className="text-sm text-slate-500">No community deals spotted right now. Check back soon!</p>
                </div>
              )}
            </div>
          )}
        </section>

        {/* CORE DASHBOARD LOGIC */}
        {activeTab === "dashboard" && token && (
          <div className="relative space-y-12 animate-in fade-in duration-500">

            {/* ⚡ THE UPGRADED FLOATING REAL-TIME ALERT */}
            {liveDropAlert && (
                <div className="fixed top-24 right-4 sm:right-6 z-[100] w-[calc(100%-2rem)] sm:w-full max-w-md bg-white rounded-3xl border border-slate-100 shadow-[0_20px_50px_rgba(0,0,0,0.12)] p-4 sm:p-5 animate-in slide-in-from-top-6 slide-in-from-right-6 fade-in duration-500">                
                <div className="flex flex-col gap-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-emerald-50 flex items-center justify-center shrink-0 animate-pulse">
                        <Zap className="w-5 h-5 text-emerald-600" />
                      </div>
                      <div>
                        <h3 className="text-[10px] font-bold text-emerald-600 uppercase tracking-wider mb-0.5">Good News! We Found a Better Price</h3>
                        <p className="text-slate-800 font-bold text-sm leading-tight max-w-[280px]">{liveDropAlert}</p>
                      </div>
                    </div>
                    <button 
                      onClick={() => setLiveDropAlert(null)} 
                      className="p-1.5 hover:bg-slate-100 text-slate-400 hover:text-slate-600 rounded-full transition-colors shrink-0"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  
                  <div className="flex gap-2">
                    <Button 
                      size="sm"
                      onClick={() => {
                        const element = document.getElementById('shopping-plan');
                        if (element) {
                          element.scrollIntoView({ behavior: 'smooth' });
                        } else {
                          if (typeof refreshDashboardMetrics === 'function') {
                            refreshDashboardMetrics();
                          }
                        }
                        setLiveDropAlert(null);
                      }} 
                      className="w-full bg-slate-900 hover:bg-slate-800 text-white rounded-full font-semibold text-xs py-4 shadow-sm"
                    >
                      See Savings
                    </Button>
                  </div>
                </div>
              </div>
            )}
            
            {/* 2. HERO SECTION */}
            {optimizedSplit && optimizedSplit.net_savings > 0 && (
              <section className="bg-white rounded-[32px] p-8 sm:p-12 shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-slate-100 flex flex-col md:flex-row items-center justify-between gap-8 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-50 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none" />
                <div className="space-y-1 z-10 text-center md:text-left w-full md:w-auto">
                  <p className="font-semibold text-slate-500 tracking-wide uppercase text-sm">You could save</p>
                  <h1 className="text-5xl sm:text-6xl font-extrabold tracking-tighter text-emerald-600">
                    £{optimizedSplit.net_savings.toFixed(2)}
                  </h1>
                </div>
                
                <div className="flex flex-col gap-3 z-10 w-full md:w-auto min-w-[240px]">
                  <Button className="w-full bg-slate-900 hover:bg-slate-800 text-white rounded-xl py-6 font-semibold text-base shadow-lg" onClick={() => document.getElementById('shopping-plan')?.scrollIntoView({ behavior: 'smooth' })}>
                    See My Shopping Plan
                  </Button>
                  <Button variant="outline" className="w-full rounded-xl py-6 font-semibold text-base" onClick={() => setActiveTab("catalog")}>
                    Browse Items
                  </Button>
                </div>
              </section>
            )}

            {/* 3. TRANSFORMED ROUTE OPTIMIZATION (SHOPPING PLAN) */}
            {optimizedSplit && (
              <section id="shopping-plan" className="space-y-6 scroll-mt-24">
                <div className="flex justify-between items-end">
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900">Best Shopping Plan</h2>
                  {optimizedSplit.net_savings === 0 && (
                    <span className="text-sm font-semibold text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
                      One-Store Option
                    </span>
                  )}
                </div>
                <div className="grid md:grid-cols-2 gap-6">
                  {(() => {
                    const groupedAllocations = optimizedSplit.allocations.reduce((acc: any, alloc: any) => {
                      const store = alloc.allocated_store || "Unknown";
                      if (!acc[store]) acc[store] = [];
                      acc[store].push(alloc);
                      return acc;
                    }, {});

                    return Object.entries(groupedAllocations).map(([storeName, items]: [string, any]) => {
                      const storeTotal = items.reduce((sum: number, item: any) => sum + item.total_cost, 0);
                      return (
                        <div key={storeName} className="bg-white rounded-3xl p-6 shadow-sm border border-slate-200/50 flex flex-col justify-between">
                          <div>
                            <div className="flex justify-between items-end mb-2">
                              <div>
                                <h3 className="text-lg font-bold text-slate-900">{storeName}</h3>
                              </div>
                              <span className="text-xl font-bold text-emerald-600">£{storeTotal.toFixed(2)}</span>
                            </div>
                            <p className="text-sm text-slate-500 font-medium mb-4">Buy these items here:</p>
                            
                            <div className="max-h-[220px] overflow-y-auto pr-1 space-y-3 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-slate-200 [&::-webkit-scrollbar-thumb]:rounded-full">
                              {items.map((alloc: any, idx: number) => (
                                <div key={idx} className="flex justify-between items-center text-sm font-medium text-slate-700 bg-slate-50 rounded-xl px-4 py-3 mr-1">
                                  <div className="flex items-center gap-3 max-w-[70%]">
                                    <div className="w-5 h-5 rounded-full bg-emerald-100 flex items-center justify-center shrink-0">
                                      <Check className="w-3 h-3 text-emerald-600" />
                                    </div>
                                    <span className="truncate">{alloc.item_name}</span>
                                  </div>
                                  <span className="shrink-0 font-semibold text-slate-900">£{alloc.total_cost.toFixed(2)}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>
                      );
                    });
                  })()}
                </div>
              </section>
            )}

            {/* 4. SIMPLIFIED BASKET */}
            <section className="space-y-6">
              <div className="flex justify-between items-end">
                <div>
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900">Your Basket</h2>
                </div>
              </div>

              {basketItems.length === 0 ? (
                <div className="text-center py-20 bg-white rounded-3xl border border-dashed border-slate-200">
                  <ShoppingBasket className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <h3 className="text-lg font-semibold text-slate-700">Basket is empty</h3>
                  <p className="text-slate-400 text-sm mt-1 mb-6">Add some items to your basket and we'll help you find the cheapest places to shop.</p>
                  <Button variant="outline" className="rounded-full font-semibold" onClick={() => setActiveTab("catalog")}>Browse Items</Button>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {basketItems.map((item) => {
                    const { minPrice, bestStore } = getCheapestPrice(item.prices);
                    return (
                      <div key={item.id} className="bg-white rounded-2xl p-5 shadow-[0_2px_10px_rgba(0,0,0,0.02)] border border-slate-100 hover:border-slate-200 transition-all flex flex-col group">
                        
                        <div className="flex justify-between items-start mb-4">
                          <div className="pr-4">
                            <h3 className="font-bold text-slate-900 text-base leading-tight">{item.name}</h3>
                            <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{item.category}</span>
                          </div>
                          <button onClick={() => handleModifyQuantity(item.id, item.quantity, "delete")} className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-300 hover:bg-rose-50 hover:text-rose-500 rounded-lg transition-all shrink-0">
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>

                        <div className="flex items-center gap-3 mb-4">
                          <div className="flex items-center bg-slate-50 rounded-lg border border-slate-100 p-0.5">
                            <button onClick={() => handleModifyQuantity(item.id, item.quantity, "decrement")} className="p-1.5 text-slate-400 hover:text-slate-900"><Minus className="w-3.5 h-3.5" /></button>
                            <span className="w-6 text-center font-semibold text-sm">{item.quantity}</span>
                            <button onClick={() => handleModifyQuantity(item.id, item.quantity, "increment")} className="p-1.5 text-slate-400 hover:text-slate-900"><Plus className="w-3.5 h-3.5" /></button>
                          </div>
                          {minPrice !== null && (
                            <div className="flex flex-col">
                              <span className="text-[10px] font-semibold text-emerald-600 uppercase">Best Price</span>
                              <span className="font-bold text-slate-900 text-lg">£{(minPrice * item.quantity).toFixed(2)} <span className="text-xs text-slate-400 font-medium">@ {bestStore}</span></span>
                            </div>
                          )}
                        </div>

                        <details className="mt-auto pt-4 border-t border-slate-50 group/details">
                          <summary className="text-xs font-semibold text-slate-500 cursor-pointer list-none flex items-center justify-between hover:text-slate-700 transition-colors">
                            Compare prices
                            <ChevronDown className="w-3.5 h-3.5 group-open/details:rotate-180 transition-transform" />
                          </summary>
                          <div className="mt-3 grid grid-cols-2 gap-y-2 text-xs">
                            {availableStores.map(store => {
                              const data = item.prices[store];
                              const isBest = store === bestStore;
                              return (
                                <div key={store} className={`flex items-center gap-1.5 ${!data ? 'opacity-40' : ''}`}>
                                  {data ? <Check className={`w-3.5 h-3.5 ${isBest ? 'text-emerald-500' : 'text-slate-300'}`} /> : <Minus className="w-3.5 h-3.5 text-slate-300" />}
                                  <span className={isBest ? 'font-semibold text-slate-800' : 'text-slate-500'}>{store}</span>
                                  {data && <span className="ml-auto font-mono text-slate-500 pr-2">£{(data.price * item.quantity).toFixed(2)}</span>}
                                </div>
                              );
                            })}
                          </div>
                        </details>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            {/* 5. ADVANCED INSIGHTS (COLLAPSIBLE) */}
            <section className="pt-8 border-t border-slate-200/60">
              <button 
                onClick={() => setShowAdvancedInsights(!showAdvancedInsights)}
                className="flex items-center justify-between w-full p-4 bg-white rounded-2xl border border-slate-200/60 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-slate-100 rounded-xl text-slate-600"><Info className="w-4 h-4" /></div>
                  <span className="font-semibold text-slate-800 text-sm">More Details & Recent Receipts</span>
                </div>
                {showAdvancedInsights ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
              </button>

              {showAdvancedInsights && (
                <div className="grid md:grid-cols-2 gap-6 mt-6 animate-in fade-in slide-in-from-top-4">
                  {basketOptions.length > 0 && (
                    <div className="bg-white rounded-3xl p-6 border border-slate-200/60 shadow-sm flex flex-col max-h-[300px]">
                      <h3 className="font-bold text-slate-800 mb-4">Compare Store Prices</h3>
                      <div className="space-y-3 overflow-y-auto pr-2 custom-scrollbar">
                        {basketOptions.map((option, index) => {
                          const diff = option.total_cost - basketOptions[0].total_cost;
                          
                          return (
                            <div key={option.store_name} className="flex justify-between items-center p-3 rounded-xl border border-slate-100 bg-slate-50/50 hover:bg-slate-50 transition-colors">
                              <div className="flex items-center gap-3">
                                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs shrink-0 ${index === 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-500'}`}>
                                  {index + 1}
                                </div>
                                <div>
                                  <p className="font-bold text-slate-900 text-sm">{option.store_name}</p>
                                  <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">{option.items_counted} of {basketItems.length} items found</p>
                                </div>
                              </div>
                              <div className="text-right">
                                <span className="block font-bold text-slate-700">£{option.total_cost.toFixed(2)}</span>
                                {index > 0 && diff > 0 && (
                                  <span className="block text-[10px] font-bold text-rose-500">+£{diff.toFixed(2)}</span>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {receiptsHistory.length > 0 && (
                    <div className="bg-white rounded-3xl p-6 border border-slate-200/60 shadow-sm">
                      <h3 className="font-bold text-slate-800 mb-4 flex items-center gap-2"><Receipt className="w-4 h-4 text-slate-400" /> Recent Receipts</h3>
                      <div className="space-y-2 max-h-[200px] overflow-y-auto pr-2">
                        {receiptsHistory.map(receipt => (
                          <div key={receipt.id} onClick={() => handleViewReceipt(receipt.id)} className="flex justify-between items-center p-3 rounded-xl hover:bg-slate-50 cursor-pointer border border-transparent hover:border-slate-100 transition-all">
                            <div>
                              <p className="font-semibold text-sm text-slate-800">{receipt.store_name}</p>
                              <p className="text-[10px] font-bold text-slate-400 uppercase mt-0.5">{receipt.date}</p>
                            </div>
                            <span className="font-bold text-slate-600">£{receipt.total_spent.toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>
          </div>
        )}

        {/* CATALOGUE TAB */}
        {activeTab === "catalog" && (
           <div className="space-y-6 animate-in fade-in duration-500">
             <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
               <div>
                 <h2 className="text-2xl font-bold tracking-tight text-slate-900">Browse Items</h2>
                 <p className="text-sm text-slate-500">Search for items to add to your list.</p>
               </div>
               <div className="relative w-full sm:w-80">
                 <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                 <input type="text" placeholder="Search groceries..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-11 pr-4 py-3 bg-white border border-slate-200 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent shadow-sm" />
               </div>
             </div>

             <div className="bg-white rounded-3xl shadow-[0_2px_10px_rgba(0,0,0,0.02)] border border-slate-100 overflow-hidden">
                <div className="divide-y divide-slate-100">
                  {displayedCatalogItems.map((item) => {
                    const existingQty = basketItems.find(bi => bi.name === item.canonical_name)?.quantity || 0;
                    const isExpanded = expandedItemId === item.id;
                    return (
                      <div key={item.id} className="group">
                        <div onClick={() => handleRowToggle(item.id)} className="flex items-center justify-between p-4 hover:bg-slate-50 cursor-pointer transition-colors">
                          <div className="flex items-center gap-4">
                            <ChevronRight className={`w-4 h-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                            <div>
                              <p className="font-semibold text-slate-900">{item.canonical_name}</p>
                              <div className="flex items-center gap-2 mt-1">
                                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{item.category}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-semibold">{item.variant_count} stores</span>
                              </div>
                            </div>
                          </div>
                          <Button size="sm" variant={existingQty > 0 ? "secondary" : "default"} onClick={(e) => { e.stopPropagation(); handleAddItem(item.id); }} disabled={actionId !== null} className={`rounded-full px-4 font-semibold text-xs ${existingQty > 0 ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100' : 'bg-slate-900 text-white'}`}>
                            {actionId === item.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : existingQty > 0 ? <span className="flex items-center gap-1"><Check className="w-3 h-3" /> Added ({existingQty})</span> : <span className="flex items-center gap-1"><Plus className="w-3 h-3" /> Add</span>}
                          </Button>
                        </div>
                        
                        {isExpanded && (
                          <div className="bg-slate-50/50 p-6 border-t border-slate-100 text-sm">
                            {loadingVariants ? <div className="text-slate-400 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin"/> Loading prices...</div> : itemVariants.length === 0 ? <p className="text-slate-400">No cross-store data.</p> : (
                              <div className="grid gap-2 max-w-md">
                                {itemVariants.map((v, i) => (
                                  <div key={i} className="flex justify-between items-center bg-white p-3 rounded-xl border border-slate-100 shadow-sm">
                                    <span className="font-semibold text-slate-700">{v.store_name} <span className="font-normal text-slate-400 text-xs ml-2">"{v.raw_name}"</span></span>
                                    <span className="font-bold text-slate-900">£{v.price.toFixed(2)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {displayedCatalogItems.length === 0 && <div className="p-8 text-center text-slate-400">No items found.</div>}
                </div>
             </div>
           </div>
        )}

        {/* LOGGED OUT STATE */}
        {!token && activeTab === "dashboard" && (
          <div className="py-32 text-center animate-in fade-in duration-500 max-w-lg mx-auto">
            <div className="w-20 h-20 bg-white rounded-3xl shadow-sm border border-slate-100 flex items-center justify-center mx-auto mb-6 transform rotate-3">
              <ShoppingBasket className="w-8 h-8 text-emerald-600" />
            </div>
            <h1 className="text-4xl font-extrabold tracking-tight text-slate-900 mb-4">Shop smarter, not harder.</h1>
            <p className="text-slate-500 mb-8 text-lg">SmartBasket compares grocery prices across top UK supermarkets to build you the perfect, money-saving shopping route.</p>
            <Button onClick={() => setShowAuthModal(true)} className="bg-slate-900 hover:bg-slate-800 text-white rounded-full px-8 py-6 font-semibold text-lg shadow-xl shadow-slate-900/10 transition-transform active:scale-95">Get Started</Button>
          </div>
        )}
      </div>

      {/* 6. FLOATING ACTION BUTTON (UPLOAD RECEIPT) */}
      {token && (
        <>
          <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleReceiptUpload} />
          <button 
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="fixed bottom-8 right-8 z-40 bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-4 rounded-full shadow-[0_8px_30px_rgb(16,185,129,0.3)] font-bold text-sm flex items-center gap-2 transition-transform hover:scale-105 active:scale-95 group disabled:opacity-70 disabled:hover:scale-100"
          >
            {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Camera className="w-5 h-5 group-hover:-rotate-12 transition-transform" />}
            <span className="hidden sm:block">{uploading ? "Scanning..." : "Scan Receipt"}</span>
          </button>
        </>
      )}

      {/* MODALS & OVERLAYS */}
      {showAuthModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/20 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-md bg-white rounded-[32px] shadow-2xl p-8 relative">
            <button onClick={() => setShowAuthModal(false)} className="absolute right-6 top-6 text-slate-400 hover:bg-slate-100 p-2 rounded-full"><X className="w-5 h-5"/></button>
            <div className="w-12 h-12 rounded-2xl bg-emerald-50 flex items-center justify-center mb-6"><Lock className="w-5 h-5 text-emerald-600"/></div>
            <h2 className="text-2xl font-extrabold text-slate-900 mb-2">{isAuthRegister ? "Create account" : "Welcome back"}</h2>
            <p className="text-slate-500 text-sm mb-8">{isAuthRegister ? "Start tracking prices and saving money today." : "Sign in to access your custom shopping plans."}</p>
            <form onSubmit={handleAuthSubmission} className="space-y-4">
              {authModalError && <div className="p-3 bg-rose-50 text-rose-600 rounded-xl text-xs font-semibold">{authModalError}</div>}
              <div>
                <input type="text" placeholder="Username" value={authUsername} onChange={e => {setAuthUsername(e.target.value); setFieldErrors({});}} className={`w-full bg-slate-50 border ${fieldErrors.username ? 'border-rose-300' : 'border-slate-200'} rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900`} />
              </div>
              {isAuthRegister && (
                <div>
                  <input type="email" placeholder="Email" value={authEmail} onChange={e => {setAuthEmail(e.target.value); setFieldErrors({});}} className={`w-full bg-slate-50 border ${fieldErrors.email ? 'border-rose-300' : 'border-slate-200'} rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900`} />
                </div>
              )}
              <div>
                <input type="password" placeholder="Password" value={authPassword} onChange={e => {setAuthPassword(e.target.value); setFieldErrors({});}} className={`w-full bg-slate-50 border ${fieldErrors.password ? 'border-rose-300' : 'border-slate-200'} rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900`} />
              </div>
              <Button type="submit" disabled={authLoading} className="w-full bg-slate-900 text-white rounded-xl py-6 font-semibold shadow-md mt-2">{authLoading ? <Loader2 className="w-5 h-5 animate-spin"/> : isAuthRegister ? "Create Account" : "Sign In"}</Button>
            </form>
            <button onClick={() => setIsAuthRegister(!isAuthRegister)} className="w-full text-center text-sm font-semibold text-slate-500 mt-6 hover:text-slate-900">{isAuthRegister ? "Already have an account?" : "Need an account?"}</button>
          </div>
        </div>
      )}

      {viewReceipt && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/20 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-md bg-white rounded-[32px] shadow-2xl overflow-hidden relative flex flex-col max-h-[85vh]">
            <div className="p-6 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
              <div>
                <h3 className="font-bold text-slate-900 text-lg">{viewReceipt.store_name}</h3>
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">{viewReceipt.date}</p>
              </div>
              <button onClick={() => setViewReceipt(null)} className="p-2 bg-white rounded-full shadow-sm hover:bg-slate-100"><X className="w-4 h-4 text-slate-600"/></button>
            </div>
            <div className="p-6 overflow-y-auto space-y-4 flex-1">
              {viewReceipt.items.map((item, i) => (
                <div key={i} className="flex justify-between items-center">
                  <div>
                    <p className="font-semibold text-slate-800 text-sm">{item.name}</p>
                    <p className="text-[10px] text-slate-400 uppercase font-bold">{item.category}</p>
                  </div>
                  <span className="font-mono font-bold text-slate-600">£{item.price.toFixed(2)}</span>
                </div>
              ))}
            </div>
            <div className="p-6 bg-slate-900 text-white flex justify-between items-center">
              <span className="font-semibold">Total Spent</span>
              <span className="text-2xl font-bold">£{viewReceipt.total_spent.toFixed(2)}</span>
            </div>
          </div>
        </div>
      )}

      <SmartBasketPlusModal isOpen={isPremiumModalOpen} onClose={() => setIsPremiumModalOpen(false)} />
      {toastNotice && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 animate-in slide-in-from-bottom-4 fade-in">
          <div className="bg-slate-900 text-white px-5 py-3 rounded-full shadow-2xl text-sm font-semibold flex items-center gap-2">
            {toastNotice.type === 'success' && <Check className="w-4 h-4 text-emerald-400"/>}
            {toastNotice.type === 'error' && <AlertCircle className="w-4 h-4 text-rose-400"/>}
            {toastNotice.text}
          </div>
        </div>
      )}
    </main>
  );
}