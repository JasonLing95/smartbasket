import React from 'react';
import { Sparkles, Mail, TrendingDown, Sliders, X } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function SmartBasketPlusModal({ isOpen, onClose }: ModalProps) {
  if (!isOpen) return null;

  const benefits = [
    {
      icon: <Mail className="h-6 w-6 text-amber-500" />,
      title: "Get email alerts when prices drop",
      description: "Receive automated email alerts the exact second a price drop hits—even when you're completely offline."
    },
    {
      icon: <TrendingDown className="h-6 w-6 text-indigo-500" />,
      title: "See when prices are likely to get cheaper",
      description: "Access historical trend models across major UK supermarkets to know precisely when to buy in bulk."
    },
    {
      icon: <Sliders className="h-6 w-6 text-emerald-500" />,
      title: "Adjust travel costs to match your preferences",
      description: "Fine-tune your personal travel limits to control how easily your list gets split between different stores."
    }
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-800 bg-slate-950 p-6 text-slate-100 shadow-2xl transition-all">
        
        <button onClick={onClose} className="absolute right-4 top-4 rounded-full p-1 text-slate-400 hover:bg-slate-900 hover:text-slate-200 transition-colors">
          <X className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-2 mb-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 text-slate-950 shadow-md">
            <Sparkles className="h-4 w-4 stroke-[2.5]" />
          </span>
          <h2 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-amber-400 via-orange-400 to-amber-200 bg-clip-text text-transparent">
            Save More With SmartBasket+
          </h2>
        </div>
        
        <p className="text-sm text-slate-400 mb-6">
          Get alerts, track price trends, and save even more every week.
        </p>

        <div className="space-y-5 mb-8">
          {benefits.map((benefit, idx) => (
            <div key={idx} className="flex gap-4 items-start rounded-xl border border-slate-900 bg-slate-900/40 p-4">
              <div className="mt-0.5 rounded-lg bg-slate-950 p-2 border border-slate-800">
                {benefit.icon}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-slate-200 text-sm">{benefit.title}</h3>
                </div>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{benefit.description}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-xl bg-gradient-to-b from-slate-900 to-slate-950 p-4 border border-slate-800/80 text-center">
          <div className="flex items-baseline justify-center gap-1 mb-3">
            <span className="text-3xl font-extrabold text-white">£2.99</span>
            <span className="text-xs text-slate-400">/ month</span>
          </div>
          
          <button 
            onClick={() => alert("Demo Mode: Subscriptions are coming soon.")}
            className="w-full rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 py-3 font-medium text-slate-950 shadow-lg shadow-orange-500/20 hover:opacity-95 transition-all text-sm tracking-wide font-semibold"
          >
            Start 7-Day Free Trial
          </button>
          
          <p className="text-[10px] text-slate-500 mt-2">
            Cancel anytime.
          </p>
        </div>

      </div>
    </div>
  );
}